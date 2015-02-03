#!python3
# This is a very simple implementation of the UCT Monte Carlo Tree Search algorithm in Python 2.7.
# The function UCT(rootstate, itermax, verbose = False) is towards the bottom of the code.
# It aims to have the clearest and simplest possible code, and for the sake of clarity, the code
# is orders of magnitude less efficient than it could be made, particularly by using a
# state.GetRandomMove() or state.DoRandomRollout() function.
#
# Example GameState classes for Nim, OXO and Othello are included to give some idea of how you
# can write your own GameState use UCT in your 2-player game. Change the game to be played in
# the UCTPlayGame() function at the bottom of the code.
#
# Written by Peter Cowling, Ed Powley, Daniel Whitehouse (University of York, UK) September 2012.
#
# Licence is granted to freely use and distribute for any sensible/legal purpose so long as this comment
# remains in any distributed code.
#
# For more information about Monte Carlo Tree Search check out our web site at www.mcts.ai

from math import *
import random
from hearthbreaker.game_objects import *
from hearthbreaker.targeting import *
from hearthbreaker.constants import *
from tests.testing_utils import generate_game_for
from hearthbreaker.agents.basic_agents import DoNothingBot
# from hearthbreaker.constants import CHARACTER_CLASS
from hearthbreaker.cards.spells.mage import ArcaneMissiles
# from hearthbreaker.cards.minions.neutral import CairneBloodhoof
deck1 = ArcaneMissiles
deck2 = ArcaneMissiles
game = generate_game_for(deck1, deck2, DoNothingBot, DoNothingBot)
game.players[0].hero.health = 6
game.players[1].hero.health = 6
game._start_turn()
""" Currently have some issues with both AIs convinced that they are winning
    so one AI will always pass his turn and the other will just kill him
"""


class HearthState:
    """ A state of the game, i.e. the game board. These are the only functions which are
        absolutely necessary to implement UCT in any 2-player complete information deterministic
        zero-sum game, although they can be enhanced and made quicker, for example by using a
        GetRandomMove() function to generate a random move during rollout.
        By convention the players are numbered 1 and 2.
    """
    def __init__(self, game):
        self.game = game
        self.activePlayer = 0

    def Clone(self):
        """ Create a deep clone of this game state.
        """
        st = HearthState(copy.deepcopy(self.game))
        st.activePlayer = self.activePlayer
        return st

    def DoMove(self, move):
        """ Update a state by carrying out the given move.
            Must update activePlayer.
        """
        if self.game.players[1].hero.health <= 0 or self.game.players[0].hero.health <= 0:
            return

        def _choose_target(targets):   # Can this ever be none?
            return targets[move[4]]

        def _choose_index(targets, player):
            return move[4]

        # print(str(self.game.current_player.mana) + "/" + str(self.game.current_player.max_mana))
        if move[0] == "end_turn":
            self.game._end_turn()
            self.game._start_turn()
            self.activePlayer = 1 - self.activePlayer
            # print("Player " + str(self.activePlayer) + " ends turn")
        elif move[0] == "hero_power":
            self.game.current_player.agent.choose_target = _choose_target
            self.game.current_player.hero.power.use()
        elif move[0] == "summon_minion":
            self.game.current_player.agent.choose_index = _choose_index
            self.game.play_card(self.game.current_player.hand[move[3]])
        elif move[2] is None:  # Passing index rather than object, hopefully the game copy fix will help with this
            self.game.play_card(self.game.current_player.hand[move[3]])
        elif move[0] == "minion_attack" or move[0] == "hero_attack" or move[0] == "mage_power":
            self.game.current_player.agent.choose_target = _choose_target
            self.game.current_player.minions[move[3]].attack()
        elif move[0] == "targeted_spell":
            self.game.current_player.agent.choose_target = _choose_target
            self.game.play_card(self.game.current_player.hand[move[3]])
            # print(str(move[0]) + " used with target " + str(move[2]))
        else:
            raise NameError("DoMove ran into unclassified card", move)

    def GetMoves(self):
        """ Get all possible moves from this state.
            Going to return tuples, untargeted_spell, targeted_spell, equip_weapon,
            play_secret, mininion_attack, hero_attack, hero_power, end_turn
        """
        if self.game.players[1].hero.health <= 0 or self.game.players[0].hero.health <= 0:
            return []
        valid_moves = []  # Move format is [string, attacker/card, target, attacker/card index, target index]

        for card in copy.copy(self.game.current_player.hand):
            dupe = False
            for i in range(len(valid_moves)):
                if valid_moves[i][1].name == card.name:
                    dupe = True
                    break
            if not dupe:
                if card.can_use(self.game.current_player, self.game) and isinstance(card, MinionCard):
                    valid_moves.append(["summon_minion", card, None, self.game.current_player.hand.index(card), 0])
                elif card.can_use(self.game.current_player, self.game) and isinstance(card, WeaponCard):
                    valid_moves.append(["equip_weapon", card, None, self.game.current_player.hand.index(card), 0])
                elif card.can_use(self.game.current_player, self.game) and isinstance(card, SecretCard):
                    valid_moves.append(["played_secret", card, None, self.game.current_player.hand.index(card), 0])
                elif card.can_use(self.game.current_player, self.game) and not card.targetable:
                    valid_moves.append(["untargeted_spell", card, None, self.game.current_player.hand.index(card), 0])
                elif card.can_use(self.game.current_player, self.game) and card.targetable:
                    for i in range(len(card.targets)):
                        valid_moves.append(["targeted_spell", card, card.targets[i],
                                           self.game.current_player.hand.index(card), i])

        found_taunt = False
        targets = []
        for enemy in self.game.other_player.minions:
            if enemy.taunt and enemy.can_be_attacked():
                found_taunt = True
            if enemy.can_be_attacked():
                targets.append(enemy)

        if found_taunt:
            targets = [target for target in targets if target.taunt]
        else:
            targets.append(self.game.other_player.hero)

        for minion in copy.copy(self.game.current_player.minions):
            if minion.can_attack():
                for i in range(len(targets)):
                    valid_moves.append(["minion_attack", minion, targets[i],
                                       self.game.current_player.minions.index(minion), i])

        if self.game.current_player.hero.can_attack():
            for i in range(len(targets)):
                valid_moves.append(["hero_attack", self.game.current_player.hero, targets[i],
                                   self.game.current_player.hand.index(card), i])
        """
        if self.game.current_player.hero.character_class == CHARACTER_CLASS.MAGE and \
           self.game.current_player.hero.power.can_use():  # some issues with indexes not matching between games
            for target in hearthbreaker.targeting.find_enemy_spell_target(game, lambda x: True):
                valid_moves.append(["hero_power", self.game.current_player.hero, target, 0, \
                                   hearthbreaker.targeting.find_spell_target(self.game, lambda t: \
                                   t.spell_targetable()).index(target)])  # need to get index things
        elif self.game.current_player.hero.character_class == CHARACTER_CLASS.PRIEST and \
             self.game.current_player.hero.power.can_use():
            for target in hearthbreaker.targeting.find_friendly_spell_target(game, lambda x: \
                                                                             x.health != x.calculate_max_health()):
                valid_moves.append(["hero_power", self.game.current_player.hero, target, 0, \
                                   hearthbreaker.targeting.find_spell_target(self.game, lambda t: \
                                                                             t.spell_targetable()).index(target)])
        elif self.game.current_player.hero.power.can_use():
            valid_moves.append(["hero_power", self.game.current_player.hero, None])
        """
        valid_moves.append(["end_turn", None, None])
        return valid_moves
        """
        s = ""
        for move in valid_moves:
            if move[0] == "minion_attack":
                if move[2] == self.game.other_player.hero:
                    s += "[" + str(move[0]) + ", " + str(move[1].card.name) + ", Enemy Hero] "
                else:
                    s += "[" + str(move[0]) + ", " + str(move[1].card.name) + ", " + str(move[2].card.name) + "] "
            elif move[0] == "hero_attack":
                if move[2] == self.game.other_player.hero:
                    s += "[" + str(move[0]) + ", Friendly Hero, Enemy Hero] "
                else:
                    s += "[" + str(move[0]) + ", Friendly Hero, " + str(move[2].card.name) + "] "
            elif move[0] == "hero_power":
                if move[2] is not None:
                    if move[2] == self.game.other_player.hero:
                        s += "[" + str(move[0]) + ", " + CHARACTER_CLASS.to_str(move[1].character_class) \
                             + ", Enemy Hero] "
                    else:
                        s += "[" + str(move[0]) + ", " + CHARACTER_CLASS.to_str(move[1].character_class) \
                             + ", " + str(move[2].card.name) + "] "
                else:
                    s += "[" + str(move[0]) + ", " + CHARACTER_CLASS.to_str(move[1].character_class) + ", " \
                         + str(move[2]) + "] "
            elif move[0] == "end_turn":
                s += "[" + str(move[0]) + ", " + str(move[1]) + ", " + str(move[2]) + "] "
            elif move[0] == "summon_minion":
                s += "[" + str(move[0]) + ", " + str(move[1].name) + ", " + str(move[2]) + "] "
            elif move[2] is None:
                s += "[" + str(move[0]) + ", " + str(move[1].name) + ", " + str(move[2]) + "] "
            elif move[0] == "targeted_spell":
                if move[2] == self.game.other_player.hero:
                    s += "[" + str(move[0]) + ", " + str(move[1].name) + ", Enemy Hero] "
                elif move[2] == self.game.current_player.hero:
                    s += "[" + str(move[0]) + ", " + str(move[1].name) + ", Friendly Hero] "
                else:
                    s += "[" + str(move[0]) + ", " + str(move[1].name) + ", " + str(move[2].card.name) + "] "
        # print(s)
        """

    def GetResult(self, player):
        """ Get the game result from the viewpoint of playerActive.
        """
        assert self.game.players[0].hero.health <= 0 or self.game.players[1].hero.health <= 0
        assert self.game.game_ended
        if self.game.players[0].hero.health <= 0 and self.game.players[1].hero.health <= 0:
            return .5
        if self.game.players[player].hero.health <= 0:
            return 0
        if self.game.players[1 - player].hero.health <= 0:
            return 1

    def __repr__(self):
        s = "[" + str(self.game.players[0].hero.health) + " hp:(" + str(self.game.players[0].mana) + "/" \
        + str(self.game.players[0].max_mana) + "):" + str(len(self.game.players[0].hand)) \
            + " in hand:" + str(self.game.players[0].deck.left) + " in deck] "
        for minion in copy.copy(self.game.players[0].minions):
            s += str(minion.calculate_attack()) + "/" + str(minion.health) + ":"
        s += "\n[" + str(self.game.players[1].hero.health) + " hp:(" +str(self.game.players[1].mana) + "/" \
        + str(self.game.players[1].max_mana) + "):" + str(len(self.game.players[1].hand)) \
             + " in hand:" + str(self.game.players[1].deck.left) + " in deck] "
        for minion in copy.copy(self.game.players[1].minions):
            s += str(minion.calculate_attack()) + "/" + str(minion.health) + ":"
        s += "\n" + "Current Player: " + str(self.activePlayer)
        return s


class NimState:
    """ A state of the game Nim. In Nim, players alternately take 1,2 or 3 chips with the
        winner being the player to take the last chip.
        In Nim any initial state of the form 4n+k for k = 1,2,3 is a win for player 1
        (by choosing k) chips.
        Any initial state of the form 4n is a win for player 2.
    """
    def __init__(self, ch):
        self.activePlayer = 1  # At the root pretend the player just moved is p1 - p0 has the first move
        self.chips = ch

    def Clone(self):
        """ Create a deep clone of this game state.
        """
        st = NimState(self.chips)
        st.activePlayer = self.activePlayer
        return st

    def DoMove(self, move):
        """ Update a state by carrying out the given move.
            Must update activePlayer.
        """
        assert move >= 1 and move <= 3 and move == int(move)
        self.chips -= move
        self.activePlayer = 1 - self.activePlayer

    def GetMoves(self):
        """ Get all possible moves from this state.
        """
        return list(range(1, min([4, self.chips + 1])))

    def GetResult(self, playerjm):
        """ Get the game result from the viewpoint of playerjm.
        """
        assert self.chips == 0
        if self.activePlayer == playerjm:
            return 1  # playerjm took the last chip and has won
        else:
            return 0  # playerjm's opponent took the last chip and has won

    def __repr__(self):
        s = "Chips:" + str(self.chips) + " JustPlayed:" + str(self.activePlayer)
        return s


class Node:
    """ A node in the game tree. Note wins is always from the viewpoint of activePlayer.
        Crashes if state not specified.
    """
    def __init__(self, move=None, parent=None, state=None):
        self.move = move  # the move that got us to this node - "None" for the root node
        self.parentNode = parent  # "None" for the root node
        self.childNodes = []
        self.wins = 0
        self.visits = 0
        if not move or move[0] != "end_turn":
            self.untriedMoves = state.GetMoves()  # future child nodes
        else:
            self.untriedMoves = []  # daniel's fix?
        self.activePlayer = state.activePlayer  # the only part of the state that the Node needs later
        self.state = state

    def UCTSelectChild(self):
        """ Use the UCB1 formula to select a child node. Often a constant UCTK is applied so we have
            lambda c: c.wins/c.visits + UCTK * sqrt(2*log(self.visits)/c.visits to vary the amount of
            exploration versus exploitation.
        """
        s = sorted(self.childNodes, key=lambda c: c.wins / c.visits + sqrt(2 * log(self.visits) / c.visits))[-1]
        return s

    def AddChild(self, m, s):
        """ Remove m from untriedMoves and add a new child node for this move.
            Return the added child node
        """
        n = Node(move=m, parent=self, state=s)
        self.untriedMoves = [x for x in self.untriedMoves if x != m]
        self.childNodes.append(n)
        return n

    def Update(self, result):
        """ Update this node - one additional visit and result additional wins.
            result must be from the viewpoint of activePlayer.
        """
        self.visits += 1
        self.wins += result

    def __repr__(self):
        t = ""
        a = ""
        if self.move == None:
            return "None"
        if self.move[2] == None:
            a += "!!!HOLD ON THIS IS WRONG!!!"
        elif self.move[2] == self.state.game.other_player.hero:  # Are copies messing this up?
            a += "Enemy Hero"
        elif self.move[2] == self.state.game.current_player.hero:
            a += "Own Hero"
        else:
            a += str(self.move[2]) + str(self.state.game.other_player.hero) + str(self.state.game.current_player.hero)

        if self.move[0] == "end_turn":
            t += "End Turn"
        elif self.move[0] == "targeted_spell":
            t += "Cast [" + str(self.move[1].name) + "] on " + a
        elif self.move[0] == "untargeted_spell":
            t += "Cast [" + str(self.move[1].name) + "]"
        
            
        return str(int(100 * self.wins / self.visits)) + "% " + t + "     W/V:" \
               + str(int(self.wins)) + "/" + str(self.visits) + " U:" + str(self.untriedMoves)

    def TreeToString(self, indent):
        s = self.IndentString(indent) + str(self)
        for c in self.childNodes:
            s += c.TreeToString(indent + 1)
        return s

    def IndentString(self, indent):
        s = "\n"
        for i in range(1, indent + 1):
            s += "| "
        return s

    def ChildrenToString(self):
        s = ""
        for c in self.childNodes:
            s += str(c) + "\n"
        return s

    def clean(self):
        for child in self.childNodes:
            child.clean()
        del self.childNodes
        del self.parentNode
        del self.untriedMoves

def UCT(rootstate, itermax, verbose=False):
    """ Conduct a UCT search for itermax iterations starting from rootstate.
        Return the best move from the rootstate.
        Assumes 2 alternating players (player 1 starts), with game results in the range [0.0, 1.0].
    """

    rootnode = Node(state=rootstate)

    for i in range(itermax):
        node = rootnode
        state = rootstate.Clone()

        # Select
        while node.untriedMoves == [] and node.childNodes != []:  # node is fully expanded and non-terminal
            node = node.UCTSelectChild()
            state.DoMove(node.move)

        # Expand
        if node.untriedMoves != []:  # if we can expand (i.e. state/node is non-terminal)
            m = random.choice(node.untriedMoves)
            state.DoMove(m)
            node = node.AddChild(m, state)  # add child and descend tree

        # Rollout - this can often be made orders of magnitude quicker using a state.GetRandomMove() function
        while state.GetMoves() != []:  # while state is non-terminal
            state.DoMove(random.choice(state.GetMoves()))

        # Backpropagate
        while node is not None:  # backpropagate from the expanded node and work back to the root node
            node.Update(state.GetResult(node.activePlayer))
            # state is terminal. Update node with result from POV of node.activePlayer
            node = node.parentNode

    # Output some information about the tree - can be omitted
    if (verbose):
        print(rootnode.TreeToString(0))
    else:
        print(rootnode.ChildrenToString())

    bestmove = sorted(rootnode.childNodes, key=lambda c: c.visits)[-1].move  # return the move that was most visited
    rootnode.clean()
    del rootnode
    
    return bestmove

def UCTPlayGame():
    """ Play a sample game between two UCT players where each player gets a different number
        of UCT iterations (= simulations = tree nodes).
    """
    # state = NimState(15)  # uncomment to play Nim with the given number of starting chips
    state = HearthState(game)
    while (state.GetMoves() != []):
        print(str(state))
        if state.activePlayer == 1:
            m = UCT(rootstate=state, itermax=1000, verbose=False)
        else:
            m = UCT(rootstate=state, itermax=1000, verbose=False)
        print("Best Move: " + str(m) + "\n")
        state.DoMove(m)
    if state.GetResult(state.activePlayer) == 1:
        print("Player " + str(state.activePlayer) + " wins!" + "\n" + str(state))
    elif state.GetResult(state.activePlayer) == 0:
        print("Player " + str(1 - state.activePlayer) + " wins!" + "\n" + str(state))
    else:
        print("Nobody wins!")
    # raw_input("[Close]")

if __name__ == "__main__":
    """ Play a single game to the end using UCT for both players.
    """
    UCTPlayGame()
