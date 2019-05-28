#!/usr/bin/env python
# -*- coding: utf-8 -*-
from locales.localization import LangTuple
from locales.emoji_utils import emote_dict
from fight import standart_actions, weapons, ai, statuses, armors, abilities, items
from bot_utils.keyboards import *
import random
import engine
import image_generator
from PIL import Image
import file_manager


class Unit:
    control_class = None
    unit_name = 'unit'
    unit_size = 'standard'
    emote = '?'
    types = ['alive']
    summoned = False
    standart_additional = ['move', 'move_back', 'skip']
    experience = 10
    danger = 10
    image = './files/images/units/default.png'

    # Список предметов, выпадающих из юнита при убийстве. Имеет вид [name: (quantity, chance)]
    default_loot = []
    # Вероятности, с которыми Вы можете получить оружие, броню или предметы цели при её смерти
    default_loot_chances = {'armor': 0, 'weapon': 0, 'items': 0}

    def __init__(self, name, controller=None, unit_dict=None, fight=None, complexity=None):

        # То, как осуществляется управление юнитом
        self.controller = controller
        self.unit_name_marker = self.unit_name
        if controller is not None:
            self.controller.unit = self
        self.done = False
        self.active = True
        self.loot = self.default_loot
        self.loot_chances = self.default_loot_chances
        # Список доступных действий для клавиатуры

        # Параметры игрока
        self.name = name
        self.id = engine.rand_id()
        self.fight = fight
        self.team = None
        self.lang = None
        self.melee_accuracy = 0
        self.range_accuracy = 0
        self.evasion = 0
        self.damage = 0
        self.spell_damage = 0
        self.energy = 0
        self.speed = 9
        self.weapon = weapons.Fist(self)
        self.weapons = []
        self.abilities = []
        self.items = []
        self.armor = []
        self.inventory = []

        # Параметры для боя
        self.default_weapon = weapons.Fist(self)
        self.lost_weapon = []
        self.boosted_attributes = {}

        # Временные параметры
        self.blocked_damage = 0
        self.dmg_received = 0
        self.wasted_energy = 0
        self.hp_delta = 0
        self.melee_targets = []
        self.statuses = {}
        self.target = None
        self.action = []
        self.disabled = []
        self.hp_changed = False
        self.weapon_to_member = []

        # Параметры для ai
        self.number = 1
        self.named = True

    def available_actions(self):
        actions = [(1, WeaponButton(self, self.weapon)), (1, MoveForward(self)), (1, self.weapon.reload_button()),
                   (3, AdditionalKeyboard(self))]
        return actions

    def equip_from_dict(self, unit_dict):
        for key, value in unit_dict.items():
            setattr(self, key, value)
        if unit_dict['weapon'] is not None:
            self.weapon = weapons.weapon_dict[unit_dict['weapon']['name']](self, obj_dict=unit_dict['weapon'])
        else:
            self.weapon = weapons.weapon_dict[self.default_weapon](self)
        self.weapons = []
        self.abilities = [abilities.ability_dict[ability['name']](self, obj_dict=ability) for ability in unit_dict['abilities']]
        self.items = engine.Container(base_dict=unit_dict['inventory']).fight_list(self)
        self.inventory = engine.Container(base_dict=unit_dict['inventory']).inv_list(self)
        self.armor = [armors.armor_dict[armor['name']](self, obj_dict=armor) for armor in unit_dict['armor']]

    def additional_actions(self):
        actions = [(1, MoveForward(self)),
                   (1, MoveBack(self)),
                   (2, PickUpButton(self)),
                   (2, SkipButton(self)),
                    (3, PutOutButton(self))]
        return actions

    # -----------------------  Функции создания картинки -------------------

    def get_image(self):
        # сформированная картинка, размер юнита, отступ сверху из-за слишком большого оружия
        image = file_manager.my_path + self.image[1:]
        return Image.open(image), self.unit_size, (0, 0)

    def get_unit_image_dict(self):
        return {
            'one-handed':
                {
                    'file': './files/images/dummy.png',
                    'right_hand': (30, 320),
                    'left_hand': (220, 320),
                    'body_armor': (110, 200),
                    'head': (111, 30),
                    'width_padding': 0
                },
            'two-handed':
                {
                    'file': './files/images/dummy_twohanded.png',
                    'right_hand': (15, 160),
                    'left_hand': (307, 320),
                    'body_armor': (197, 200),
                    'head': (199, 30),
                    'width_padding': 60
                },
            'covers':
                {
                    'hand_one_handed':
                        {
                            'file': './files/images/cover_arm.png',
                            'coordinates': (-3, 108)
                        },
                    'scarf':
                        {
                            'file': './files/images/cover_scarf.png',
                            'coordinates': (47 + 87 if self.weapon.image_pose == 'two-handed' else 47, 90)
                        },
                }
        }

    def get_hairstyle(self):
        import hairstyles
        return random.choice([hairstyles.Hairstyle_2])()

    def calculate_base_image_parameters(self, unit_image_dict, equipment_dicts):
        base = unit_image_dict['file']
        image = Image.open(base)
        width, height = image.size
        left_padding = 0
        right_padding = 0
        top_padding = self.get_hairstyle().passed_padding[1] if not any(armor.placement == 'head' and armor.covering for armor in self.armor) else 0
        for dct in equipment_dicts:
            handle_x, handle_y = dct['handle']
            placement = dct['placement']
            placement_x, placement_y = unit_image_dict[placement]
            left_padding = handle_x - placement_x if handle_x - placement_x > left_padding else left_padding
            pot_right_padding = (placement_x - handle_x + Image.open(dct['file']).size[0]) - width
            right_padding = pot_right_padding if pot_right_padding > right_padding else right_padding
            top_padding = handle_y - placement_y if handle_y - placement_y > top_padding else top_padding
        return left_padding + width + right_padding, height + top_padding, top_padding, left_padding

    def add_head(self, pil_image, top_padding, left_padding):
        if not any(armor.placement == 'head' and armor.covering for armor in self.armor):
            hairstyle = self.get_hairstyle()
            hairstyle_image = Image.open(hairstyle.path)
            hairstyle_x, hairstyle_y = hairstyle.padding
            head_coord_tuple_x, head_coord_tuple_y = self.get_unit_image_dict()[self.weapon.image_pose]['head']
            pil_image.paste(hairstyle_image, (head_coord_tuple_x - hairstyle_x + left_padding,
                                              head_coord_tuple_y - hairstyle_y + top_padding),
                            mask=hairstyle_image)
            return pil_image
        else:
            return pil_image

    def construct_image(self):
        unit_image_dict = self.get_unit_image_dict()[self.weapon.image_pose]
        equipment_dicts = []
        weapon_image_dict = self.weapon.get_image_dict()
        if weapon_image_dict is not None:
            equipment_dicts.append(weapon_image_dict)
        for armor in self.armor:
            if armor.get_image_dict() is not None:
                equipment_dicts.append(armor.get_image_dict())
        base_width, base_height, top_padding, left_padding = self.calculate_base_image_parameters(unit_image_dict,
                                                                                                  equipment_dicts)
        base_png = Image.new('RGBA', (base_width, base_height), (255, 0, 0, 0))
        base_png.paste(Image.open(unit_image_dict['file']), (left_padding, top_padding))
        base_png = self.add_head(base_png, top_padding, left_padding)
        equipment_dicts.sort(key=lambda i: i['layer'], reverse=True)
        for equipment in equipment_dicts:
            handle_x, handle_y = equipment['handle']
            placement = equipment['placement']
            placement_x, placement_y = unit_image_dict[placement]
            covered = equipment['covered']
            equipment_image = Image.open(equipment['file'])

            base_png.paste(equipment_image,
                           (placement_x - handle_x + left_padding, placement_y - handle_y + top_padding),
                            mask=equipment_image)
            if covered == 'hand_two_handed':
                base_png = self.add_head(base_png, top_padding, left_padding)
            elif covered:
                cover_dict = self.get_unit_image_dict()['covers'][covered]

                cover = Image.open(cover_dict['file'])
                cover_x, cover_y = cover_dict['coordinates']
                base_png.paste(cover, (cover_x + left_padding, cover_y + top_padding), mask=cover)
        return base_png, (left_padding + unit_image_dict['width_padding'], top_padding)

    def image_as_io(self):
        return image_generator.io_from_PIL(self.construct_image()[0])

    # -----------------------  Менеджмент энергии и жизней -----------------------------

    def recovery(self):
        pass

    def add_energy(self, number):
        pass

    def waste_energy(self, energy):
        self.wasted_energy += energy

    def change_hp(self, hp):
        self.hp_delta += hp
        self.hp_changed = True

    def speed_penalty(self):
        weight = self.weapon.weight
        for armor in self.armor:
            weight += armor.weight
        return weight

    def get_speed(self):
        return self.speed - self.speed_penalty()

    # -----------------------  Функции, связанные с оружием -----------------------------

    def equip_weapon(self, weapon):
        self.weapon = weapon

    def lose_weapon(self):
        weapon = self.weapon
        self.lost_weapon.append(weapon)
        weapon.get_lost()
        if self.weapon == weapon:
            self.equip_weapon(standart_actions.object_dict[self.default_weapon](self))

    def pick_up_weapon(self):
        weapon = self.lost_weapon[0]
        self.get_weapon(weapon)
        self.lost_weapon.remove(weapon)
        return weapon

    def change_weapon(self):
        if len(self.weapons) > 1:
            self.weapon = self.weapons[0 if self.weapon == self.weapons[1] else 1]
        else:
            self.weapon = self.weapons[0]

    def get_weapon(self, weapon):
        self.weapon = weapon

    @staticmethod
    def get_hit_chance(weapon):
        # Шанс попасть в противника из заданного оружия
        return weapon.get_hit_chance()

    def add_weapon(self, weapon):
        self.weapon = weapon
        self.weapons.append(weapon)

    def change_attribute(self, attr, value):
        if hasattr(self, attr):
            setattr(self, attr, (getattr(self, attr) + value))

    # -----------------------  Функции, связанные с броней -----------------------------

    def equip_armor(self, armor):
        self.armor.append(self)

    # ------------------------  Менеджмент целей и движение -----------------

    def targets(self):
        return [unit for unit in self.fight.units if unit not in self.team.units and unit.alive()]

    def get_melee_targets(self):
        return [unit for unit in self.melee_targets if unit.alive()]

    def get_allies(self):
        return list([unit for unit in self.team.units if unit.alive()])

    def get_targets(self):
        for unit in self.melee_targets:
            if not unit.alive():
                self.melee_targets.remove(unit)

    def move_back(self):
        for actor in self.targets():
            if self in actor.melee_targets:
                actor.melee_targets.remove(self)
        self.melee_targets = []

    def move_forward(self):
        units_to_melee = [unit for unit in self.targets() if 'forward' in unit.action]
        if not units_to_melee:
            units_to_melee = self.targets()
        for unit in units_to_melee:
            if unit not in self.melee_targets:
                unit.melee_targets.append(self)
                self.melee_targets.append(unit)
        statuses.Running(self, 1)

    # ------------------------- Активация способностей -------------------

    def activate_statuses(self, sp_type=None, action=None):
        for k, v in self.statuses.items():
            if sp_type is not None:
                if sp_type in v.types and self.alive():
                    v.act(action=action)
            else:
                if self.alive() or 'permanent' in v.types:
                    v.act()

    def activate_abilities(self, sp_type, action=None):
        for ability in self.abilities:
            if sp_type in ability.types:
                ability.act(action=action)

    def on_hit(self, action):
        self.activate_statuses('on_hit', action=action)
        self.activate_abilities('on_hit', action=action)

    def on_spell(self, spell):
        if spell.dmg_done > 0:
            spell.dmg_done += self.spell_damage
        self.activate_statuses('on_spell', action=spell)
        self.activate_abilities('on_spell', action=spell)

    def receive_hit(self, action):
        # Применение брони
        if action.dmg_done > 0:
            self.activate_statuses('receive_hit', action=action)
        if action.dmg_done > 0:
            armor_data = self.activate_armor(action.dmg_done)
            if armor_data[0] >= action.dmg_done:
                action.dmg_done = 0
                action.armored = armor_data[1]
            self.activate_abilities('receive_hit', action)

    def receive_spell(self, spell):
        self.activate_statuses('receive_spell', action=spell)
        self.activate_abilities('receive_spell', action=spell)
        if spell.dmg_done > 0:
            self.receive_damage(spell.dmg_done)

    def activate_passives(self):
        self.activate_abilities('passive')

    def actions(self):
        return [action for action in self.fight.action_queue.action_list if action.unit == self]

    # -------------------------- Функции сообщений бота ---------------------

    def get_status_string(self):
        statuses_info = []
        for key, value in self.statuses.items():
            if value.menu_string():
                statuses_info.append(value.menu_string())
        return '|'.join(statuses_info)

    def add_armor_string(self):
        for key in self.act_armor_dict:
            armor_string = LangTuple('fight', 'armor', format_dict={'actor': self.name,
                                                                    'damage_blocked': self.act_armor_dict[key],
                                                                    'armor': LangTuple('armor', key)})
            standart_actions.AddString(armor_string, 22, self)
        self.act_armor_dict = {}

    def info_string(self):
        pass

    def menu_string(self):
        pass

    def start_abilities(self):
        for ability in self.abilities:
            if 'start' in ability.types:
                ability.start_act()

    def announce(self, lang_tuple, image=None):
        self.fight.announce(lang_tuple, image=image)

    # ---------------------------- Методы боя ------------------------------

    def refresh(self):
        self.dmg_received = 0
        self.active = False
        self.target = None
        self.action = []
        self.hp_changed = False
        self.controller.talked = False

    def alive(self):
        pass

    def activate_armor(self, dmg_done):
        if not self.armor:
            return 0, None
        armor = list(self.armor)
        armor.sort(key=lambda x: x.rating)
        blocked_damage = 0
        acted_piece = None
        for piece in armor:
            chance = piece.coverage
            if engine.roll_chance(chance):
                blocked_damage = piece.block(dmg_done)
                acted_piece = piece
                break
        return blocked_damage, acted_piece

    def receive_damage(self, dmg_done):
        # Получение урона
        damage = dmg_done
        self.dmg_received += damage if damage > 0 else 0

    def lose_round(self):
        pass

    def dies(self):
        if not self.alive() and self not in self.fight.dead:
            self.fight.string_tuple.row(LangTuple('fight', 'death', format_dict={'actor': self.name}))
            return True
        return False
    # ---------------------------- Служебные методы ------------------------------

    def __str__(self):
        return str(self.id)

    def end_turn(self):
        self.controller.end_turn()

    def get_action(self, edit=False):
        self.controller.get_action(edit=edit)

    def stats(self):
        pass

    def clear(self):
        for armor in self.armor:
            armor.clear()
        for weapon in [*self.lost_weapon, *self.weapon_to_member]:
            self.inventory.append(weapon)

    def to_string(self, string, format_dict=None):
        lang_tuple = localization.LangTuple('unit_' + self.unit_name, string, format_dict=format_dict)
        return lang_tuple

    def string(self, string, format_dict=None, order=0):
        lang_tuple = self.to_string(string, format_dict=format_dict)
        if not order:
            self.fight.string_tuple.row(lang_tuple)
        else:
            standart_actions.AddString(lang_tuple=lang_tuple, unit=self, order=order)

    @staticmethod
    def create_action(name, func, button_name, order=5):
        if name not in standart_actions.action_dict:
            standart_actions.UnitAction(name, func, button_name, order=order)
        return standart_actions.action_dict[name]

    @staticmethod
    def generate_ability(name, func, button_name, order=5, cd=0):
        if name not in standart_actions.action_dict:
            standart_actions.AbilityFactory(name, func, button_name, order=order, cd=cd)
        return standart_actions.action_dict[name]

    def action_button(self, name, button_name, available):
            button = FightButton(button_name, self, name, special='unit_' + self.unit_name)
            button.available = available
            return button

    def boost_attribute(self, key, value):
        if key in self.boosted_attributes:
            self.boosted_attributes[key] += value
        else:
            self.boosted_attributes[key] = value

    def form_ai_name(self):
        same_class_units = [unit for unit in self.fight.units if unit.unit_name_marker == self.unit_name_marker and not unit.named]
        if self.number == any(unit.number for unit in same_class_units):
            self.number = len(same_class_units) + 1
        if self.number == 1:
            self.name = localization.LangTuple('unit_' + self.unit_name, 'name')
        else:
            self.name = localization.LangTuple('unit_' + self.unit_name,
                                               'name-number', format_dict={'number': self.number})

    def summon_unit(self, unit_class, name=None, unit_dict=None, **kwargs):
        new_unit = self.fight.add_ai(unit_class, name=name, unit_dict=unit_dict, **kwargs)
        new_unit.team = self.team
        new_unit.weapon = weapons.weapon_dict[new_unit.default_weapon](new_unit)
        self.team.units.append(new_unit)
        new_unit.summoned = True
        return new_unit

    @staticmethod
    def get_dungeon_format_dict(member, inventory, inventory_fill):

        return {'name': member.name,
                'hp': member['hp'],
                'max_hp': member['max_hp'] - member['hp'],
                'equipment': member.inventory.get_equipment_string(member.lang),
                'inventory': inventory, 'fill': inventory_fill}

    # Выдавание конечного списка лута при смерти.
    def generate_loot(self):
        if self.lost_weapon:
            self.weapon = self.lost_weapon[0]
        elif self.weapon_to_member:
            self.weapon = self.weapon_to_member[0]
        loot = engine.Container()
        for item in self.loot:
            if engine.roll_chance(item[1][1]):
                loot.put(item[0], value=item[1][0])
        if engine.roll_chance(self.loot_chances['weapon']) and not self.weapon.natural:
            loot.put(self.weapon.name)
        for piece in self.armor:
            if engine.roll_chance(self.loot_chances['armor']):
                loot.put(piece.name)
        for item in self.items:
            if engine.roll_chance(self.loot_chances['items']):
                loot.put(item.name)
        return loot


class StandardCreature(Unit):

    danger = 7

    def __init__(self, name, controller=None, fight=None, unit_dict=None, complexity=None):
        Unit.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        # Максимальные параметры
        self.max_hp = 4
        self.hp = self.max_hp
        self.max_energy = 5
        self.toughness = 5
        self.recovery_energy = 5
        self.melee_accuracy = 0
        self.range_accuracy = 0
        self.evasion = 0
        self.damage = 0
        self.default_weapon = 'fist'
        self.weapons = []
        self.abilities = []
        self.items = []
        self.armor = []
        self.inventory = []
        if unit_dict is not None:
            self.equip_from_dict(unit_dict)
        self.energy = int(self.max_energy/2 + 1)

    def to_dict(self):
        unit_dict = {
            'unit_name': self.unit_name,
            'name': self.name,
            'max_hp': self.max_hp,
            'hp': self.hp,
            'max_energy': self.max_energy,
            'recovery_energy': self.recovery_energy,
            'melee_accuracy': self.melee_accuracy,
            'range_accuracy': self.range_accuracy,
            'spell_damage': self.spell_damage,
            'evasion': self.evasion,
            'damage': self.damage,
            'toughness': self.toughness,
            'abilities': [ability.to_dict() for ability in self.abilities],
            'inventory': engine.Container(base_list=[*[item.to_dict() for item in self.items], *[item.to_dict() for item in self.inventory]]).base_dict,
            'armor': [armor.to_dict() for armor in self.armor],
            'weapon': self.weapon
        }
        if unit_dict['weapon'] is not None:
            if unit_dict['weapon'].natural:
                unit_dict['weapon'] = None
            else:
                unit_dict['weapon'] = unit_dict['weapon'].to_dict()
        for key in self.boosted_attributes:
            unit_dict[key] -= self.boosted_attributes[key]
        if unit_dict['hp'] < 1:
            unit_dict['hp'] = 1
        return unit_dict

    def recovery(self):
        speed = self.get_speed() if self.get_speed() > 2 else 2
        self.energy += speed if speed < self.max_energy else self.max_energy
        self.weapon.recovery()
        return speed if speed < self.max_energy else self.max_energy

    def add_energy(self, number):
        self.energy += number
        self.max_energy += number
        self.recovery_energy += number

    def info_string(self, lang=None):
        lang = self.lang if lang is None else lang
        ability_list = ', '.join([LangTuple('abilities_' + ability.name, 'name').translate(lang)
                                  for ability in self.abilities if 'tech' not in ability.types])
        item_list = ', '.join([LangTuple('items_' + item.name, 'button').translate(lang)
                               for item in self.items])
        return LangTuple('utils', 'full_info', format_dict={'actor': self.name,
                                                            'hp': self.hp,
                                                            'energy': self.energy,
                                                            'abilities': ability_list,
                                                            'items': item_list})

    def menu_string(self):
        if len(self.weapon.targets()) != 1 or self.weapon.special_types:
            return LangTuple('unit_' + self.unit_name, 'player_menu',
                             format_dict={'actor': self.name, 'hp': self.hp,
                                          'energy': self.energy, 'weapon': LangTuple('weapon_'
                                                                                     + self.weapon.name, 'name'),
                                          'statuses': self.get_status_string()})
        else:
            menu_string = LangTuple('unit_' + self.unit_name, 'player_menu',
                             format_dict={'actor': self.name, 'hp': self.hp,
                                          'energy': self.energy, 'weapon': LangTuple('weapon_'
                                                                                     + self.weapon.name, 'name'),
                                          'statuses': self.get_status_string()}).translate(self.controller.lang)
            menu_string += '\n'
            menu_string += self.weapon.get_menu_string(short_menu=True, target=self.weapon.targets()[0].name).translate(self.controller.lang)
            return menu_string

    def refresh(self):
        Unit.refresh(self)
        self.wasted_energy = 0
        self.hp_delta = 0
        if self.energy < 0:
            self.energy = 0
        elif self.energy > self.max_energy:
            self.energy = self.max_energy

    def alive(self):
        if self.hp > 0:
            return True
        else:
            return False

    def lose_round(self):
        if self.dmg_received > 0:
            toughness = self.toughness if self.toughness > 1 else 2
            self.hp_delta -= 1 + self.dmg_received // toughness


class Necromancer(StandardCreature):
    unit_name = 'necromancer'
    emote = emote_dict['skeleton_em']

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        Unit.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        # Максимальные параметры
        self.max_hp = 4
        self.hp = self.max_hp
        self.max_energy = 5
        self.toughness = 6
        self.recovery_energy = 5
        self.melee_accuracy = 0
        self.range_accuracy = 0
        self.evasion = 0
        self.damage = 0
        self.weapon = weapons.Knife(self)
        self.weapons = []
        self.abilities = [abilities.Witch(self), abilities.Necromancer(self)]
        self.items = []
        self.armor = []
        self.inventory = []
        if unit_dict is not None:
            self.equip_from_dict(unit_dict)
        self.energy = self.max_energy

    def to_dict(self):
        unit_dict = {
            'unit_name': self.unit_name,
            'name': self.name,
            'max_hp': self.max_hp,
            'hp': self.hp,
            'max_energy': self.max_energy,
            'recovery_energy': self.recovery_energy,
            'melee_accuracy': self.melee_accuracy,
            'range_accuracy': self.range_accuracy,
            'evasion': self.evasion,
            'damage': self.damage,
            'toughness': self.toughness,
            'abilities': [ability.to_dict() for ability in self.abilities],
            'inventory': [*[item.to_dict() for item in self.items], *[item.to_dict() for item in self.inventory]],
            'armor': [armor.to_dict() for armor in self.armor],
            'weapon': self.weapon.to_dict()
        }
        for key in self.boosted_attributes:
            unit_dict[key] -= self.boosted_attributes[key]
        if unit_dict['hp'] < 1:
            unit_dict['hp'] = 1
        return unit_dict

    def recovery(self):
        if self.recovery_energy:
            self.energy += self.recovery_energy
        else:
            self.energy = self.max_energy
        self.weapon.recovery()

    def add_energy(self, number):
        self.energy += number
        self.max_energy += number
        self.recovery_energy += number

    def info_string(self, lang=None):
        lang = self.lang if lang is None else lang
        ability_list = ', '.join([LangTuple('abilities_' + ability.name, 'name').translate(lang)
                                  for ability in self.abilities if 'tech' not in ability.types])
        item_list = ', '.join([LangTuple('items_' + item.name, 'button').translate(lang)
                               for item in self.items])
        return LangTuple('utils', 'full_info', format_dict={'actor': self.name,
                                                            'hp': self.hp,
                                                            'energy': self.energy,
                                                            'abilities': ability_list,
                                                            'items': item_list})

    def menu_string(self):
        return LangTuple('unit_' + self.unit_name, 'player_menu',
                         format_dict={'actor': self.name, 'hp': self.hp,
                                      'energy': self.energy, 'weapon': LangTuple('weapon_'
                                                                                 + self.weapon.name, 'name'),
                                      'statuses': self.get_status_string()})

    def refresh(self):
        Unit.refresh(self)
        self.wasted_energy = 0
        self.hp_delta = 0
        if self.energy < 0:
            self.energy = 0
        elif self.energy > self.max_energy:
            self.energy = self.max_energy

    def alive(self):
        if self.hp > 0:
            return True
        else:
            return False

    def lose_round(self):
        if self.dmg_received > 0:
            self.hp_delta -= 1 + self.dmg_received // self.toughness


class Pyromant(StandardCreature):
    unit_name = 'human'

    def __init__(self, name, controller=None, fight=None, unit_dict=None, complexity=None):
        Unit.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        # Максимальные параметры
        self.max_hp = 4
        self.hp = self.max_hp
        self.max_energy = 5
        self.toughness = 6
        self.recovery_energy = 5
        self.melee_accuracy = 0
        self.range_accuracy = 0
        self.evasion = 0
        self.damage = 0
        self.weapon = random.choice([weapons.Crossbow, weapons.Hatchet, weapons.Spear])(self)
        self.weapons = []
        self.abilities = [abilities.Muscle(self)]
        self.items = [items.Bandages(self), items.Bandages(self), items.Adrenalin(self)]
        self.armor = []
        self.inventory = []
        if unit_dict is not None:
            self.equip_from_dict(unit_dict)
        self.energy = self.max_energy

    def to_dict(self):
        unit_dict = {
            'unit_name': self.unit_name,
            'name': self.name,
            'max_hp': self.max_hp,
            'hp': self.hp,
            'max_energy': self.max_energy,
            'recovery_energy': self.recovery_energy,
            'melee_accuracy': self.melee_accuracy,
            'range_accuracy': self.range_accuracy,
            'evasion': self.evasion,
            'damage': self.damage,
            'toughness': self.toughness,
            'abilities': [ability.to_dict() for ability in self.abilities],
            'inventory': [*[item.to_dict() for item in self.items], *[item.to_dict() for item in self.inventory]],
            'armor': [armor.to_dict() for armor in self.armor],
            'weapon': self.weapon.to_dict()
        }
        for key in self.boosted_attributes:
            unit_dict[key] -= self.boosted_attributes[key]
        if unit_dict['hp'] < 1:
            unit_dict['hp'] = 1
        return unit_dict

    def recovery(self):
        if self.recovery_energy:
            self.energy += self.recovery_energy
        else:
            self.energy = self.max_energy
        self.weapon.recovery()

    def add_energy(self, number):
        self.energy += number
        self.max_energy += number
        self.recovery_energy += number

    def info_string(self, lang=None):
        lang = self.lang if lang is None else lang
        ability_list = ', '.join([LangTuple('abilities_' + ability.name, 'name').translate(lang)
                                  for ability in self.abilities if 'tech' not in ability.types])
        item_list = ', '.join([LangTuple('items_' + item.name, 'button').translate(lang)
                               for item in self.items])
        return LangTuple('utils', 'full_info', format_dict={'actor': self.name,
                                                            'hp': self.hp,
                                                            'energy': self.energy,
                                                            'abilities': ability_list,
                                                            'items': item_list})

    def menu_string(self):
        return LangTuple('unit_' + self.unit_name, 'player_menu',
                         format_dict={'actor': self.name, 'hp': self.hp,
                                      'energy': self.energy, 'weapon': LangTuple('weapon_'
                                                                                 + self.weapon.name, 'name'),
                                      'statuses': self.get_status_string()})

    def refresh(self):
        Unit.refresh(self)
        self.wasted_energy = 0
        self.hp_delta = 0
        if self.energy < 0:
            self.energy = 0
        elif self.energy > self.max_energy:
            self.energy = self.max_energy

    def alive(self):
        if self.hp > 0:
            return True
        else:
            return False

    def lose_round(self):
        if self.dmg_received > 0:
            self.hp_delta -= 1 + self.dmg_received // self.toughness


class Tech(Unit):
    control_class = ai.TechAi
    types = ['tech']
    summoned = True


class Basilisk(Unit):
    unit_name = 'basilisk'
    types = ['animal', 'alive']
    emote = emote_dict['basilisk_em']
    control_class = ai.BasiliskAi

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        Unit.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        # Максимальные параметры
        self.max_hp = 5
        self.hp = self.max_hp
        self.max_energy = 6
        self.recovery_energy = 0
        self.toughness = 6
        self.melee_accuracy = 0
        self.range_accuracy = 0
        self.evasion = 0
        self.damage = 2
        self.weapon = weapons.PoisonedBloodyFangs(self)
        self.weapons = []
        self.abilities = []
        self.items = []
        self.armor = []
        self.inventory = []
        if unit_dict is not None:
            self.equip_from_dict(unit_dict)
        self.energy = int(self.max_energy/2 + 1)

        self.stun_action = self.create_action('basilisk-stun', self.stun, 'button_1', order=5)
        self.rush_action = self.create_action('basilisk-rush', self.rush, 'button_2', order=10)
        self.recovery_action = self.create_action('basilisk-recovery', self.rest, 'button_3', order=5)
        self.hurt = False
        self.stun_ready = False

    def to_dict(self):
        unit_dict = {
            'unit_name': self.unit_name,
            'name': self.name,
            'max_hp': self.max_hp,
            'hp': self.hp,
            'max_energy': self.max_energy,
            'melee_accuracy': self.melee_accuracy,
            'recovery_energy': self.recovery_energy,
            'range_accuracy': self.range_accuracy,
            'evasion': self.evasion,
            'damage': self.damage,
            'toughness': self.toughness,
            'abilities': [ability.to_dict() for ability in self.abilities],
            'inventory': [*[item.to_dict() for item in self.items], *[item.to_dict() for item in self.inventory]],
            'armor': [armor.to_dict() for armor in self.armor],
            'weapon': self.weapon.to_dict()
        }
        for key in self.boosted_attributes:
            unit_dict[key] -= self.boosted_attributes[key]
        return unit_dict

    def rest(self, action):
        unit = action.unit
        if unit.recovery_energy:
            unit.energy += unit.recovery_energy
        else:
            unit.energy = unit.max_energy
        unit.weapon.recovery()
        unit.change_hp(1)
        unit.hurt = False
        unit.stun_ready = True
        unit.string('skill_1', format_dict={'actor': action.unit.name})

    def rush(self, action):
        unit = action.unit
        for target in unit.targets():
            if target not in unit.melee_targets:
                unit.melee_targets.append(target)
                target.melee_targets.append(unit)
        statuses.Buff(unit, 'damage', 1, 1)
        unit.string('skill_2', format_dict={'actor': action.unit.name})

    def stun(self, action):
        unit = action.unit
        names = []
        unit.stun_ready = False
        for target in unit.melee_targets:
            statuses.Stun(target)
            target.receive_damage(3)
            names.append(target.name)
        if names:
            unit.string('skill_3', format_dict={'actor': unit.name, 'targets': ' ,'.join(names)})
        else:
            unit.string('skill_4', format_dict={'actor': unit.name})

    def lose_round(self):
        if self.dmg_received > 0:
            self.hp_delta -= 1 + self.dmg_received // self.toughness
            self.hurt = True

    def alive(self):
        if self.hp > 0:
            return True
        else:
            return False

    def refresh(self):
        Unit.refresh(self)
        self.wasted_energy = 0
        self.hp_delta = 0
        self.hurt = False
        if self.energy < 0:
            self.energy = 0
        elif self.energy > self.max_energy:
            self.energy = self.max_energy


# Мобы Артема

class Shadow(StandardCreature):
    unit_name = 'shadow'
    emote = emote_dict['skeleton_em']

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        StandardCreature.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        # Максимальные параметры
        self.max_hp = 3
        self.evasion = 1
        self.abilities = [abilities.WeaponSnatcher(self), abilities.Dodge(self)]
        if unit_dict is not None:
            self.equip_from_dict(unit_dict)
        self.energy = self.max_energy


# Мобы Пасюка

class SperMonster(StandardCreature):
    unit_name = 'spermonster'
    control_class = ai.SperMonsterAi
    emote = emote_dict['spermonster_em']

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        StandardCreature.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        self.max_hp = 5
        self.hp = self.max_hp
        self.toughness = 4
        self.triggered = False
        self.default_weapon = 'cock'
        self.weapon = weapons.Cock(self)
        self.abilities = [abilities.Spermonster(self)]
        self.sperm_check_action = self.create_action('sperm_check', self.sperm_check, 'button_3', order=59)

    def sperm_check(self, action):
        unit = action.unit
        if not unit.triggered and unit.hp <= 1:
            unit.triggered = True
            unit.sperm_shower(action)

    def sperm_shower(self, action):
        unit = action.unit
        target = random.choice(unit.targets())
        unit.string('skill_1', format_dict={'actor': unit.name, 'target': target.name})
        statuses.Stun(target)


class PedoBear(StandardCreature):
    unit_name = 'pedobear'
    control_class = ai.PedoBearAi
    emote = emote_dict['pedobear_em']

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        StandardCreature.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        self.find_target_action = self.create_action('find_target', self.find_target, 'button_3', order=5)
        self.hug_action = self.create_action('hug', self.hug, 'button_3', order=10)
        self.locked_in = None
        self.max_hp = 6
        self.hp = self.max_hp

    def find_target(self, action):
        unit = action.unit
        targets = unit.weapon.targets()
        target = random.choice(targets)
        unit.string('skill_1', format_dict={'actor': unit.name, 'target': unit.target.name})
        unit.locked_in = target

    def hug(self, action):
        unit = action.unit
        if 'dodge' not in unit.target.action and 'move' not in unit.target.action:
            unit.damage += 1
            unit.target.receive_damage(unit.damage)
            unit.string('skill_2', format_dict={'actor': unit.name, 'target': unit.target.name, 'damage': unit.damage})
            unit.string('skill_4', format_dict={'actor': unit.name}, order=23)
            unit.locked_in = None
        else:
            unit.string('skill_3', format_dict={'actor': unit.name, 'target': unit.target.name})
            unit.locked_in = None


# Мобы Асгард

class BirdRukh(StandardCreature):
    unit_name = 'bird_rukh'
    control_class = ai.BirdRukhAi

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        StandardCreature.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        self.fly_action = self.create_action('bird_fly', self.fly, 'button_1', order=10)
        self.stun_action = self.create_action('bird_stun', self.stun, 'button_2', order=10)
        self.weapon = weapons.RukhBeak(self)

    def stun(self, action):
        unit = action.unit
        targets = unit.targets()
        unit.string('skill_2', format_dict={'actor': unit.name})
        for target in targets:
            if 'dodge' not in target.action:
                statuses.Stun(target)
                target.receive_damage(3)

    def fly(self, action):
        unit = action.unit
        unit.move_forward()
        unit.string('skill_1', format_dict={'actor': unit.name})


class Bear(StandardCreature):
    unit_name = 'bear'
    control_class = ai.BearAi

    def __init__(self, name=None, controller=None, fight=None, unit_dict=None, complexity=None):
        StandardCreature.__init__(self, name, controller=controller, fight=fight, unit_dict=unit_dict)
        self.destroy_action = self.create_action('destroy', self.destroy, 'button_1', order=10)
        self.weapon = weapons.BearClaw(self)

    def destroy(self, action):
        unit = action.unit
        unit.damage += 3
        attack = standart_actions.BaseAttack(unit=unit, fight=unit.fight)
        attack.activate()
        unit.damage -= 3
        unit.string('skill_1', format_dict={'actor': unit.name, 'target': unit.target.name, 'damage': attack.dmg_done})

units_dict = {}

def fill_unit_dict():
    from fight.unit_files import skeleton, goblin, human, lich, rat, bloodbug, snail, worm, zombie, goblin_bomber


