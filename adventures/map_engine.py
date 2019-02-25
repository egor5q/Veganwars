from bot_utils import bot_methods
from bot_utils  .keyboards import Button, form_keyboard
from locales.emoji_utils import emote_dict
from locales.localization import LangTuple
from fight import units, items, weapons, armors
from adventures import locations
import Testing
import engine
import random


class PartyMovement:

    def __init__(self, party, start_location, end_location):
        self.party = party
        self.start_location = start_location
        self.end_location = end_location

    def execute(self, call):
        if self.party.ask_move(self.end_location, call) and self.start_location.move_permission(self, call) \
                and self.end_location.move_permission(self, call):
            self.party.move(self.end_location)


# --------------------------------------------- Карта Подземелья -----------------------------------------------------
# Объект карты подземелья
class DungeonMap:
    name = None
    wall_location = None

    def __init__(self, length, dungeon, branch_length, branch_number, new=True, dungeon_dict=None):
        self.location_matrix = dict()
        self.length = length
        self.width = 0
        self.height = 0
        self.branch_length = branch_length
        self.branch_number = branch_number
        self.entrance = None
        self.exit = None
        self.party = None
        self.dungeon = dungeon
        self.table_row = 'dungeons_' + self.name
        self.core_location_dict = {}
        self.branch_location_dict = {}
        self.generate_location_dicts()

    def generate_location_dicts(self):
        self.core_location_dict = {'end': [locations.PlaceHolder],
                                   'crossroad': [locations.PlaceHolder],
                                   'default': [locations.MobLocation]}
        self.branch_location_dict = {'end': [locations.PlaceHolder],
                                     'crossroad': [locations.PlaceHolder],
                                     'default': [locations.PlaceHolder]}

    def create_map(self):
        self.dungeon.map = self
        map_tuples = Testing.generate_core(complexity=len(self.dungeon.team)*7, length=self.length)
        for i in range(self.branch_number):
            Testing.generate_branch(map_tuples, self.branch_length)
        self.width = max(map_tuple[0] for map_tuple in map_tuples) + 1
        if self.width < 3:
            self.width = 3
        self.height = max(map_tuple[1] for map_tuple in map_tuples) + 1
        if self.height < 3:
            self.height = 3
        for x in range(0, self.width):
            for y in range(0, self.height):
                if (x, y) in map_tuples:
                    self.location_matrix[(x, y)] = self.generate_location(x, y, map_tuples[(x, y)])
                else:
                    self.location_matrix[(x, y)] = self.generate_wall(x, y)
        return self

    def generate_location(self, x, y, map_tuple):
        if x == 0 and y == 0:
            return locations.Entrance(0, 0, self.dungeon, map_tuple)
        elif 'core' in map_tuple.types:
            return self.generate_core_locations(x, y, map_tuple)
        elif  'branch' in map_tuple.types:
            return self.generate_branch_location(x, y, map_tuple)

    def generate_core_locations(self, x, y, map_tuple):
            if 'end' in map_tuple.types:
                return self.create_location(self.core_location_dict['end'], x, y, map_tuple)
            elif 'crossroad' in map_tuple.types:
                return self.create_location(self.core_location_dict['crossroad'], x, y, map_tuple)
            else:
                return self.create_location(self.core_location_dict['default'], x, y, map_tuple)

    def generate_branch_location(self, x, y, map_tuple):
            if 'end' in map_tuple.types:
                return self.create_location(self.branch_location_dict['end'], x, y, map_tuple)
            elif 'crossroad' in map_tuple.types:
                return self.create_location(self.branch_location_dict['crossroad'], x, y, map_tuple)
            else:
                return self.create_location(self.branch_location_dict['default'], x, y, map_tuple)

    def create_location(self, location_class_list, x, y, map_tuple):
        return random.choice(location_class_list)(x, y, self.dungeon, map_tuple)

    def generate_wall(self, x, y):
        return Location(x, y, self.dungeon, map_tuple=None)

    def start(self):
        #self.greetings_message()
        self.dungeon.party.move(self.dungeon.map.get_location(0, 0))

    # Возвращает локацию от координат матрицы
    def get_location(self, x, y):
        return self.location_matrix[(int(x), int(y))]

    def greetings_message(self):
        for member in self.dungeon.party.members:
            message = LangTuple(self.table_row, 'greeting').translate(member.lang)
            bot_methods.send_message(member.chat_id, message)


def get_enemy(complexity, enemy_dict):
    enemy_pool = (key for key in enemy_dict if enemy_dict[key][0] < complexity < enemy_dict[key][1])
    enemy = random.choice(list(enemy_pool))
    enemy_types = [name for name in enemy.split('+')]
    danger_dict = {enemy: units.units_dict[enemy].danger for enemy in enemy_types}
    enemy_list = []
    strongest_added = False
    while complexity >= min(list(danger_dict.values())):
        strongest_enemies = [key for key in danger_dict.keys()
                                if danger_dict[key] == max(list(danger_dict.values()))]
        if strongest_enemies != enemy_types:
            if not strongest_added:
                chosen_enemy = strongest_enemies[0]
                enemy_list.append(chosen_enemy)
                strongest_added = True
            else:
                for enemy in enemy_types:
                    if complexity < danger_dict[enemy]:
                        enemy_types.remove(enemy)
                chosen_enemy = random.choice(enemy_types)
                enemy_list.append(chosen_enemy)
        else:
            chosen_enemy = random.choice(enemy_types)
            enemy_list.append(chosen_enemy)
        complexity -= danger_dict[chosen_enemy]
    return enemy_list


# --------------------------------------------------------------------------------------------------
# Объект комнаты/локации карты
class Location:
    name = 'location'
    greet_msg = 'Тестовое приветствие локации'
    image = None
    finish = False
    emote = emote_dict['wall_em']
    visited_emote = emote_dict['visited_map_em']

    def __init__(self, x, y, dungeon, map_tuple):
        self.visited = False
        self.current = False
        self.seen = False
        self.coordinates = (x, y)
        self.x = x
        self.y = y
        self.dungeon = dungeon
        self.special = '0'
        self.mobs = None
        self.mob_team = None
        self.receipts = engine.ChatContainer()
        if map_tuple is not None:
            self.complexity = map_tuple.complexity

    # Возвращает кнопку для клавиатуры карты
    def return_button(self):
        return Button(text=self.emoji(), callback_data='map_' + str(self.dungeon.chat_id) + '_move_' + '-'.join([str(item) for item in self.coordinates]))

    def buttons(self, member):
        return list()

    def handler(self, call):
        pass

    # Возвращает эмодзи карты
    def emoji(self):
        if self.current:
            return emote_dict['current_map_em']
        elif self.visited:
            return self.visited_emote
        elif self.is_close(self.dungeon.party.current_location) or self.seen:
            return self.emote
        else:
            return emote_dict['question_em']

    def get_image(self):
        return self.image

    # Перемещение группы
    def enter_location(self, party):
        if self.mobs:
            self.mob_team = self.mobs.generate_team()
        self.image = self.get_image()
        self.current = True
        party.current_location = self
        if not self.visited:
            self.greet_party()
            for member in party.members:
                member.message_id = None
        self.on_enter()
        self.visited = True

    def greet_party(self):
        if self.greet_msg:
            self.dungeon.delete_map()
            self.dungeon.party.send_message(self.greet_msg,
                                            image=self.image)

    def available(self):
        return False

    # Проверяет, можно ли производить перемещение с данной локации
    def move_permission(self, movement, call):
        bot_methods.answer_callback_query(call, 'Вы не можете здесь пройти.', alert=False)
        return self.available()

    # Функция, запускающаяся при входе в комнату. Именно сюда планируется пихать события.
    def on_enter(self):
        self.dungeon.update_map()

    def collect_receipts(self):
        if self.receipts:
            self.dungeon.party.send_message('Вы находите следующие рецепты: {}'.format(self.receipts.to_string('rus')))
            self.dungeon.party.collected_receipts += self.receipts

    def leave_location(self):
        self.current = False

    # Функция проверяет, можно ли шагнуть из одной локации в другую
    def is_close(self, location):
        if abs(location.x - self.x) + abs(location.y - self.y) < 2:
            self.seen = True
            return True

    # Находит список локаций, расположенных вплотную к текущей
    def get_close(self):
        close_locations = []
        if self.y > 0:
            close_locations.append(self.dungeon.map.get_location(self.x, self.y-1))
        if self.y < self.dungeon.map.height - 1:
            close_locations.append(self.dungeon.map.get_location(self.x, self.y+1))
        if self.x > 0:
            close_locations.append(self.dungeon.map.get_location(self.x-1, self.y))
        if self.x < self.dungeon.map.width - 1:
            close_locations.append(self.dungeon.map.get_location(self.x+1, self.y))
        return close_locations

    # Функция проверяет, видно ли из одной локации другую
    def is_visible(self, location):
        if abs(location.x - self.x) < 2 and abs(location.y - self.y) < 2:
            return True

    # Функция возвращает список локаций, которые видно на карте из данной
    def get_visible(self):
        center_x = self.x
        center_y = self.y
        if self.y == 0:
            center_y += 1
        elif self.y == self.dungeon.map.height - 1:
            center_y -= 1
        if self.x == 0:
            center_x += 1
        elif self.x == self.dungeon.map.width - 1:
            center_x -= 1
        visible_locations_x = [center_x - 1, center_x, center_x + 1]*3
        visible_locations_y = [*[center_y - 1]*3, *[center_y]*3, *[center_y + 1]*3]
        visible_locations = list(map(self.dungeon.map.get_location, visible_locations_x, visible_locations_y))
        return visible_locations

    def create_path(self):
        self.emote = '-'

    # -------------------------------------- Методы для ориентирования вокруг локации -------------------------

    def higher(self):
        if self.y < self.dungeon.map.max_y - 1:
            return self.dungeon.map.get_location(self.x, self.y + 1)
        else:
            return None

    def lower(self):
        if self.y > 0:
            return self.dungeon.map.get_location(self.x, self.y - 1)
        else:
            return None

    def right(self):
        if self.x < self.dungeon.map.max_x - 1:
            return self.dungeon.map.get_location(self.x + 1, self.y)
        else:
            return None

    def left(self):
        if self.x > 0:
            return self.dungeon.map.get_location(self.x - 1, self.y )
        else:
            return None

    # Перевод локации в строку для сохранения

    def __str__(self):
        visited = 'visited' if self.visited else 'closed'
        return self.name + '_' + self.special + '_' + visited

    def location_fight(self):
            results = self.dungeon.run_fight(self.dungeon.party.join_fight(), self.mob_team)
            self.process_results(results)

    def process_results(self, results):
        pass


class MobPack:
    def __init__(self, *args, complexity=None):
        self.mob_units = args
        self.complexity = complexity

    def generate_team(self):
        team_dict = {}
        i = 0
        for unit in self.mob_units:
            team_dict[(units.units_dict[unit], i)] = units.units_dict[unit](complexity=self.complexity).to_dict()
            i += 1
        return team_dict


# --------------------------------------------------------------------------------------------------
# Объект группы в подземелье
