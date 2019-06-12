from adventures import map_engine
from locales import emoji_utils
from fight import fight_main, ai, items, units, armors, standart_actions
import locales.localization
from image_generator import create_dungeon_image
from bot_utils import bot_methods, keyboards
import random
import inspect
import sys
import engine
import threading
import time


class OpenLocation(map_engine.Location):

    def move_permission(self, movement, call):
        return self.available()

    def available(self):
        return True

    def get_emote(self):
        return self.default_emote


class PlaceHolder(OpenLocation):
    name = 'default_corridor'


class PlaceHolderPos(OpenLocation):
    name = 'default_corridor_positive'
    impact = 'positive'
    impact_integer = 10
    image = 'AgADAgAD7aoxG86k0UvHW9xX2r__8LxVUw8ABCxD1LsgKx-3bS4EAAEC'

    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = '+' + str(self.complexity)


class PlaceHolderNeg(OpenLocation):
    name = 'default_corridor_negative'
    impact = 'negative'
    impact_integer = 10

    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = '-' + str(self.complexity)


class End(OpenLocation):
    name = 'default_end'
    emote = '⚔'
    image = 'AgADAgADvKoxG2wBsUvh5y6JbSyZmUNqXw8ABHPt9rOstNKjRZ8FAAEC'

    def __init__(self, x, y, dungeon, map_tuple, special='0'):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)


class DeadEnd(OpenLocation):
    name = 'default_branch_end'

    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = 'X'


class CrossRoad(OpenLocation):
    name = 'default_crossroad'
    emote = emoji_utils.emote_dict['crossroad_em']

    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = '+'


class Entrance(OpenLocation):
    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = '-'

    def greet_party(self):
        pass


class Smith(OpenLocation):
    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = emoji_utils.emote_dict['smith_em']
        self.visited_emote = emoji_utils.emote_dict['smith_em']
        self.greet_msg = 'Тут возможно улучшить оружие или броню.'
        self.used_units = []

    def buttons(self, member):
        button = dict()
        button['name'] = 'Кузница'
        button['act'] = 'choice'
        return [button] if member.chat_id not in self.used_units else list()

    def handler(self, call):
        member = self.dungeon.party.member_dict[call.from_user.id]
        data = call.data.split('_')
        action = data[3]
        if action == 'choice':
            self.send_choice(member)
        if action == 'improve':
            self.improve(call, member, data[-1])

    def send_choice(self, member):
        text = 'Выберите предмет, который хотите улучшить'
        buttons = []
        valid_items = [item for item in member['inventory'] if 'improved' in item.keys()]
        if 'improved' in member['weapon']:
            valid_items.append(member['weapon'])
        for item in valid_items:
            if not item['improved']:
                buttons.append(keyboards.DungeonButton(member.inventory.get_item_name(item, member.lang), member,
                                                       'location',
                                                       'improve',
                                                       item['id'], named=True))
        buttons.append(keyboards.DungeonButton('Закрыть', member, 'menu', 'main', named=True))
        keyboard = keyboards.form_keyboard(*buttons)
        member.edit_message(text, reply_markup=keyboard)

    def improve(self, call, member, item_id):
        if member.chat_id not in self.used_units:
            member.inventory[item_id]['improved'] += 2
            member.alert('Вы улучшили предмет', call)
            self.used_units.append(member.chat_id)
            member.member_menu()


class FireBlocked(OpenLocation):
    def __init__(self, x, y, dungeon, map_tuple):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = 'ts'
        self.entrance_loc = None

    def move_permission(self, movement, call):
        if self.entrance_loc is None:
            self.entrance_loc = movement.start_location
            return True
        elif movement.end_location != self.entrance_loc and movement.end_location != self:
            if not any('torch' in member.inventory.items() for member in movement.party.members):
                bot_methods.answer_callback_query(call, 'У вас нет факела, чтобы пройти дальше', alert=True)
                return False
        return True


class MobLocation(OpenLocation):
    name = 'mobs'
    emote = '!!!'
    image = './files/images/backgrounds/default.jpg'
    impact = 'negative'
    impact_integer = 10

    def __init__(self, x, y, dungeon, map_tuple, mobs=None, loot=list()):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        mobs = map_engine.get_enemy(self.complexity, dungeon.map.enemy_list, map_tuple) if mobs is None else mobs
        self.mobs = map_engine.MobPack(*mobs, complexity=self.complexity)
        self.loot = engine.ChatContainer()
        if self.mobs is not None:
            main_mob = units.units_dict[max(mobs, key=lambda mob: units.units_dict[mob].danger)]
            self.emote = main_mob.emote
            self.greet_msg = main_mob.greet_msg

    def get_image(self):
        if not self.visited:
            image_list = []
            for mob in self.mob_team:
                unit = mob[0](None, unit_dict=self.mob_team[mob])
                image_list.append(unit.get_image())
            return create_dungeon_image(self.image, image_list)
        else:
            return None

    def on_enter(self):
        if not self.visited and self.dungeon.map.entrance != self:
            for member in self.dungeon.party.members:
                member.occupied = True
            self.dungeon.delete_map()
            thread = threading.Thread(target=self.location_fight)
            thread.start()
        else:
            self.dungeon.update_map()

    def process_results(self, results):
        if not any(unit_dict['name'] == self.dungeon.party.leader.unit_dict['name'] for unit_dict in results['winners']):
                keyboard = keyboards.form_keyboard(keyboards.DungeonButton('Покинуть карту', self, 'menu', 'defeat', named=True))
                self.dungeon.party.send_message('Вы проиграли!', reply_markup=keyboard)
        else:
            for member in self.dungeon.party.members:
                member.occupied = False
                member.unit_dict = [unit_dict for unit_dict in results['winners']
                                    if unit_dict['name'] == member.unit_dict['name']][0]
                member.inventory.update()
            loot = results['loot'] + self.loot
            experience = sum([units.units_dict[mob].experience for mob in self.mobs.mob_units if self.mobs is not None])
            self.dungeon.party.experience += experience
            print('Раздача добычи:{}'.format(loot))
            self.dungeon.party.distribute_loot(loot)
            self.collect_receipts()
            self.dungeon.update_map()


class LoseLoot(OpenLocation):
    name = 'lose_loot'
    emote = emoji_utils.emote_dict['loose_loot_em']
    greet_msg = 'Вас обдирает налоговая.'

    def on_enter(self):
        if not self.visited:
            victims = [member for member in self.dungeon.party.members if not member.inventory.is_empty()]
            if victims:
                victim = random.choice(victims)
                item = random.choice(victim.inventory.items())
                victim.inventory.remove(item)
                self.dungeon.party.send_message(victim.name + ' потерял ' + str(standart_actions.get_name(item[0]['name'], 'rus')))
            else:
                pass
            self.dungeon.update_map(new=True)
        else:
            self.dungeon.update_map()


class LootRoom(OpenLocation):
    greet_msg = 'текст-комнаты-с-лутом'
    image = 'AgADAgADCqoxG5L9kUtxN8Z8SC03ibyeOQ8ABCxbztph9fIoZfIAAgI'

    def __init__(self, x, y, dungeon, map_tuple, special='0'):
        map_engine.Location.__init__(self, x, y, dungeon, map_tuple)
        self.emote = emoji_utils.emote_dict['kaaba_em']

    def on_enter(self):
        if not self.visited:
            self.dungeon.delete_map()
            found_loot = [standart_actions.object_dict[item]().to_dict() for item in self.dungeon.map.low_loot]
            self.dungeon.party.distribute_loot(*random.choices(found_loot, k=2))
        self.dungeon.update_map()


class ForestPos(OpenLocation):
    name = 'forest_location_pos'
    impact = 'positive'
    impact_integer = 10

    def get_emote(self):
        return '+' + str(self.complexity)


class ForestNeg(OpenLocation):
    name = 'forest_location_neg'
    impact = 'negative'
    impact_integer = 10

    def get_emote(self):
        return '-' + str(self.complexity)


class ForestNeutral(OpenLocation):
    name = 'forest_location_1'

    def get_emote(self):
        return str(self.complexity)


class ForestCrossroad(OpenLocation):
    name = 'forest_location_crossroad'
    default_emote = '+'


class ForestEnd(OpenLocation):
    name = 'forest_location_end'
    default_emote = emoji_utils.emote_dict['weapon_em']


location_dict = {value.name: value for key, value
                in dict(inspect.getmembers(sys.modules[__name__], inspect.isclass)).items()
                if value.name is not None}




