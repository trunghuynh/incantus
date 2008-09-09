import copy
from pydispatch import dispatcher
from GameEvent import TokenLeavingPlay, ColorModifiedEvent, TypeModifiedEvent, SubtypeModifiedEvent, SupertypeModifiedEvent
from abilities import abilities, stacked_abilities
from characteristics import stacked_variable, stacked_characteristic
import CardDatabase

class MtGObject(object):
    #Universal dispatcher
    # this class is for all objects that can send and receive signals
    #_lock = False
    #_holding = False
    def send(self, event, *args, **named):
        #send event to dispatcher
        dispatcher.send(event, self, *args, **named)
        #if not MtGObject._lock: dispatcher.send(event, self, *args, **named)
        #else: MtGObject._holding.append(lambda: dispatcher.send(event, self, *args, **named))
    def register(self, callback, event, sender=dispatcher.Any, weak=True, expiry=-1):
        # register to receive events
        # if expiry == -1, then it is continuous, otherwise number is the number of times
        # that the callback is processed
        # XXX Major python problem - each callback must be a separate function (or wrapped in a lambda)
        # which makes it hard to disconnect it
        dispatcher.connect(callback, signal=event, sender=sender,weak=weak,expiry=expiry)
    def unregister(self, callback, event, sender=dispatcher.Any, weak=True):
        dispatcher.disconnect(callback, signal=event, sender=sender, weak=weak)
    #@staticmethod
    #def lock():
    #    MtGObject._lock = True
    #    MtGObject._holding = []
    #@staticmethod
    #def release():
    #    MtGObject._lock = False
    #    # Call the sends that were held
    #    for func in MtGObject._holding: func()

class GameObject(MtGObject):
    #__slots__ = ["name", "base_name", "base_cost", "base_text", "base_color", "base_type", "base_subtypes", "base_supertypes", "_owner", "zone", "out_play_role", "in_play_role", "stack_role", "_current_role", "key"]
    def __init__(self, owner):
        self._owner = owner
        self.zone = None

        self._current_role = None
        self.out_play_role = None
        self.in_play_role = None
        self.stack_role = None
        self._last_known_info = None
        self._overrides = set()

        # characteristics
        self.base_name = None
        self.base_cost = None
        self.base_text = None
        self.base_color = None
        self.base_type = None
        self.base_subtypes = None
        self.base_supertype = None
        self.base_abilities = abilities()
        self.play_spell = None

        self.base_power = None
        self.base_toughness = None

    owner = property(fget=lambda self: self._owner)
    def current_role():
        doc = '''The current role for this card. Either a Card (when in hand, library, graveyard or removed from game), Spell, (stack) or Permanent (in play)'''
        def fget(self): return self._current_role
        def fset(self, newrole):
            role = copy.deepcopy(newrole)
            # Set up base characteristics
            role.owner = self.owner
            role.name = stacked_variable(self.base_name)
            role.cost = self.base_cost
            role.text = stacked_variable(self.base_text)
            role.color = stacked_characteristic(self, self.base_color, ColorModifiedEvent())
            role.type = stacked_characteristic(self, self.base_type, TypeModifiedEvent())
            role.subtypes = stacked_characteristic(self, self.base_subtypes, SubtypeModifiedEvent())
            role.supertype = stacked_characteristic(self, self.base_supertype, SupertypeModifiedEvent)
            role.abilities = stacked_abilities(self, self.base_abilities)

            if self.base_power: role.base_power = stacked_variable(self.base_power)
            if self.base_toughness: role.base_toughness = stacked_variable(self.base_toughness)
            self._current_role = role
        return locals()
    current_role = property(**current_role())
    def save_lki(self):
        self._last_known_info = self._current_role
        self._last_known_info.is_LKI = True
    def move_to(self, zone, position="top"):
        zone.move_card(self, position)
    # XXX These two are just temporary
    controller = property(fget=lambda self: self._current_role.controller, fset=lambda self, c: setattr(self._current_role, "controller", c))
    # I should probably get rid of the getattr call, and make everybody refer to current_role directly
    # But that makes the code so much uglier
    def __getattr__(self, attr):
        if hasattr(self.current_role, attr):
            return getattr(self._current_role,attr)
        #else: raise Exception, "no attribute named %s"%attr
        else:
        # We are probably out of play - check the last known info
            return getattr(self._last_known_info, attr)
    def __repr__(self):
        return "%s at %s"%(str(self),str(id(self)))
    def __str__(self):
        return str(self.name)

    # Class attributes for mapping the cards
    _counter = 0
    _cardmap = {}
    def _add_to_map(self):
        self.key = (self._counter, self.base_name)
        self._cardmap[self.key] = self
        self.__class__._counter += 1

class Card(GameObject):
    def __init__(self, cardname, owner):
        super(Card, self).__init__(owner)
        # characteristics
        self.expansion = None
        self.hidden = False

        from CardRoles import SpellRole, CardRole, NoRole
        CardDatabase.loadCardFromDB(self, cardname)
        self.stack_role = SpellRole(self)
        self.current_role = self.out_play_role = CardRole(self)
        if (self.base_type == "Instant" or self.base_type == "Sorcery"):
            self.in_play_role = NoRole(self)
        self._add_to_map()

class Token(GameObject):
    def __init__(self, info, owner):
        super(Token, self).__init__(owner)
        from CardRoles import NoRole
        if type(info) == dict: info = CardDatabase.convertToTxt(info)
        CardDatabase.execCode(self, info)
        self.current_role = self.out_play_role = self.stack_role = NoRole(self)
        self._add_to_map()
    def move_to(self, zone, position="top"):
        super(Token, self).move_to(zone, position)
        if not str(zone) == "play": self.send(TokenLeavingPlay())
    def __str__(self):
        return "Token: %s"%self.name
