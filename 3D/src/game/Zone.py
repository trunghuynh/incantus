import random
from GameObjects import MtGObject
from GameEvent import CardLeavingZone, CardEnteringZone, CardLeftZone, CardEnteredZone, CardCeasesToExist, TimestepEvent, ShuffleEvent

class Zone(MtGObject):
    def __init__(self):
        self.cards = []
    def __str__(self):
        return self.name
    def __len__(self):
        return len(self.cards)
    def __iter__(self):
        # Top of the cards is the end of the list
        return iter(self.get())
    def top(self, number=1):
        if len(self) == 0: return None
        else:
            if number == 1: return self.cards[-1]
            else: return self.cards[:-(number+1):-1]
    def bottom(self, number=1):
        if len(self) == 0: return None
        else: return self.cards[:number]
    def get(self, match=lambda c: True):
        # Retrieve all of a type of Card in current location
        return [card for card in iter(self.cards[::-1]) if match(card)]
    def cease_to_exist(self, card):
        self._remove_card(card, CardCeasesToExist())
    def _remove_card(self, card, event=CardLeftZone()):
        self.cards.remove(card)
        card.zone = None
        self.send(event, card=card)
        self.after_card_removed(card)
    def _insert_card(self, card, position):
        card.zone._remove_card(card)
        self.before_card_added(card)
        if position == "top": self.cards.append(card)
        elif position == "bottom": self.cards.insert(0, card)
        else: self.cards.insert(position, card)
        card.zone = self
        self.send(CardEnteredZone(), card=card)
    def move_card(self, card, position):
        self.send(CardEnteringZone(), card=card)
        old_zone = card.zone
        old_zone.send(CardLeavingZone(), card=card)
        # Remove card from previous zone
        self._insert_card(card, position)
    # The next 2 are for zones to setup and takedown card roles
    def before_card_added(self, card):
        card.enteringZone(self.name)
    def after_card_removed(self, card):
        card.leavingZone(self.name)

class OrderedZone(Zone):
    def __init__(self):
        super(OrderedZone, self).__init__()
        self.pending = False
        self.pending_top = []
        self.pending_bottom = []
        self.register(self.commit, TimestepEvent())
    def _insert_card(self, card, position):
        self.pending = True
        if position == "top": self.pending_top.append(card)
        else: self.pending_bottom.append(card)
    def get_card_order(self, cardlist, pos):
        if len(cardlist) > 1:
            player = cardlist[0].owner
            reorder = player.getCardSelection(cardlist, len(cardlist), from_zone=str(self), from_player=player, required=False, prompt="Order cards entering %s of %s"%(pos, self))
            if reorder: cardlist = reorder[::-1]
        return cardlist
    def pre_commit(self): pass
    def post_commit(self): pass
    def commit(self):
        if self.pending_top or self.pending_bottom:
            self.pre_commit()
            for card in self.pending_top+self.pending_bottom:
                card.zone._remove_card(card)
                self.before_card_added(card)
            toplist = self.get_card_order([c for c in self.pending_top], "top")
            bottomlist = self.get_card_order([c for c in self.pending_bottom], "bottom")
            self.cards = bottomlist + self.cards + toplist
            for card in self.pending_top+self.pending_bottom:
                card.zone = self
                self.send(CardEnteredZone(), card=card)
            self.pending_top[:] = []
            self.pending_bottom[:] = []
            self.post_commit()
            self.pending = False

class OutPlayMixin(object):
    def before_card_added(self, card):
        card.current_role = card.out_play_role
        super(OutPlayMixin, self).before_card_added(card)

class Graveyard(OutPlayMixin, OrderedZone):
    name = "graveyard"

class Hand(OutPlayMixin, Zone):
    name = "hand"

class Removed(OutPlayMixin, Zone):
    name = "removed"

class AddingCardsMixin(object):
    def add_new_card(self, card, position="top"):
        self.send(CardEnteringZone(), card=card)
        self._insert_card_unordered(card, position)
    def _insert_card_unordered(self, card, position):
        # XXX Same as Zone._insert_card
        self.before_card_added(card)
        if position == "top": self.cards.append(card)
        elif position == "bottom": self.cards.insert(0, card)
        else: self.cards.insert(position, card)
        card.zone = self
        self.send(CardEnteredZone(), card=card)

class Library(OutPlayMixin, AddingCardsMixin, OrderedZone):
    def __init__(self):
        super(Library, self).__init__()
        self.needs_shuffle = False
        self.ordering = True
    def enable_ordering(self):
        self.ordering = True
    def disable_ordering(self):
        self.ordering = False
    def _insert_card(self, card, position):
        if self.ordering:
            super(Library, self)._insert_card(card, position)
        else:
            card.zone._remove_card(card)
            self._insert_card_unordered(card, position)
    def shuffle(self):
        if not self.pending: random.shuffle(self.cards)
        else: self.needs_shuffle = True
    def pre_commit(self):
        if self.needs_shuffle:
            self.needs_shuffle = False
            random.shuffle(self.cards)
            self.send(ShuffleEvent())
    name = "library"

class PlayView(object):
    def __init__(self, player, play):
        self.player = player
        self.play = play
    def get(self, match=lambda c: True, all=False):
        if all: return self.play.get(match)
        else: return [card for card in self.play if match(card) and card.controller == self.player]
    def __getattr__(self, attr):
        return getattr(self.play, attr)
    def move_card(self, card, position="top"):
        self.play.move_card(card, position, self.player)
    def add_new_card(self, card, position="top"):
        self.play.add_new_card(card, position, self.player)

class Play(AddingCardsMixin, OrderedZone):
    name = "play"
    def __init__(self, game):
        self.game = game
        self.controllers = {}
        super(Play, self).__init__()
    def get_view(self, player):
        return PlayView(player, self)
    def get_card_order(self, cardlist, pos):
        if len(cardlist) > 1:
            # Sort the cards
            player_cards = dict([(player, []) for player in self.game.players])
            for card in cardlist:
                player_cards[card.controller].append(card)
            cardlist = []
            for player in self.game.players:
                cards = player_cards[player]
                if len(cards) > 1:
                    cards = player.getCardSelection(cards, len(cards), from_zone=str(self), from_player=player, prompt="Order cards entering %s"%(self))
                    cards.reverse()
                cardlist.extend(cards)
        return cardlist
    def add_new_card(self, card, position, controller):
        self.controllers[card] = controller
        super(Play, self).add_new_card(card, position)
    def move_card(self, card, position, controller):
        self.controllers[card] = controller
        super(Play, self).move_card(card, position)
    def before_card_added(self, card):
        card.current_role = card.in_play_role
        card.controller = self.controllers[card]
        super(Play, self).before_card_added(card)
    def post_commit(self):
        self.controllers = {}

class CardStack(Zone):
    name = "stack"
