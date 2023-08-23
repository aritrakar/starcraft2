import math
import pickle
import random
import sys
import time

import cv2
import numpy as np
from sc2 import maps  # For loading maps
from sc2.bot_ai import BotAI
# Difficulty for bots, race for the 1 of 3 races
from sc2.data import Difficulty, Race
from sc2.ids.unit_typeid import UnitTypeId
from sc2.main import run_game
# Bot is what we will use to create our own bot
# Computer is pre-automated
from sc2.player import Bot, Computer

SAVE_REPLAY = True

total_steps = 10000
steps_for_pun = np.linspace(0, 1, total_steps)
step_punishment = ((np.exp(steps_for_pun**3) / 10) - 0.1) * 10


class SC2Bot(BotAI):
    async def on_step(self, iteration: int):
        no_action = True
        while no_action:
            try:
                with open('state_rwd_action.pkl', 'rb') as f:
                    state_rwd_action = pickle.load(f)

                    if (state_rwd_action['action'] is None):
                        # print("No action yet")
                        no_action = True
                    else:
                        # print("Action found")
                        no_action = False
            except:
                pass

        await self.distribute_workers()  # put idle workers back to work

        action = state_rwd_action['action']
        '''
        0: Expand (i.e. move to next spot, or build to 16: (minerals)+3 assemblers+3)
        1: Build stargate (or up to one) (evenly)
        2: Build voidray (evenly)
        3: Send scout (evenly/random/closest to enemy?)
        4: Attack (known buildings, units, then enemy base, just go in logical order.)
        5: Void Ray flee (back to base)
        '''

        # 0: Expand (i.e. move to next spot, or build to 16 (minerals)+3 assemblers+3)
        if (action == 0):
            await self.expand()

        # 1: Build a Star Gate (or up to one) (evenly)
        elif (action == 1):
            try:
                BUILDINGS = [UnitTypeId.GATEWAY,
                             UnitTypeId.CYBERNETICSCORE, UnitTypeId.STARGATE]
                # Iterate through all nexuses and see if these buildings are close
                for nexus in self.townhalls:  # ready or not?
                    for building in BUILDINGS:
                        if (not self.structures(building).closer_than(10, nexus).exists):
                            if (self.can_afford(building) and self.already_pending(building) == 0):
                                await self.build(building, near=nexus)
            except Exception as e:
                print(e)

        # 2: Build Void Ray (at a random Star Gate)
        elif (action == 2):
            try:
                # It makes sense to check if we can afford to make a VR at all
                # before going through ALL the Star Gates and checking it, because
                # if we can't, then we'll save time by not doing the loop
                if (self.can_afford(UnitTypeId.VOIDRAY)):
                    for sg in self.structures(UnitTypeId.STARGATE).ready.idle:
                        if self.can_afford(UnitTypeId.VOIDRAY):
                            sg.train(UnitTypeId.VOIDRAY)
            except Exception as e:
                print(e)

        # 3: Send scout
        elif (action == 3):
            self.explore(iteration)

        # 4: Attack (known buildings, units, then enemy base, just go in logical order.)
        elif (action == 4):
            self.attack()

        # 5: Void Ray flee (back to base)
        elif (action == 5):
            # TODO: Back to closest base?
            if (self.units(UnitTypeId.VOIDRAY).amount > 0):
                for vr in self.units(UnitTypeId.VOIDRAY):
                    vr.attack(self.start_location)

        map = self.make_map()

        # Save map image into "replays dir"
        if SAVE_REPLAY:
            cv2.imwrite(f"replays/{int(time.time())}-{iteration}.png", map)

        reward = 0

        try:
            attack_count = 0
            # Iterate through our void rays
            for voidray in self.units(UnitTypeId.VOIDRAY):
                if (voidray.is_attacking and voidray.target_in_range):
                    if (self.enemy_units.closer_than(8, voidray) or
                            self.enemy_structures.closer_than(8, voidray)):
                        # reward += 0.005 # original was 0.005, decent results, but let's 3x it.
                        reward += 0.015
                        attack_count += 1
        except Exception as e:
            print("Exception: ", e)
            reward = 0

        # Log every 100 iterations
        if (iteration % 100 == 0):
            print(
                f"Iter: {iteration}; RWD: {reward}; VR: {self.units(UnitTypeId.VOIDRAY).amount}")

        # Write the file
        data = {"state": map, "reward": reward, "action": None,
                "terminated": False}  # Empty action waiting for the next one!

        with open('state_rwd_action.pkl', 'wb') as f:
            pickle.dump(data, f)

    async def expand(self):
        try:
            found_something = False
            if (self.supply_left < 4):
                # Build Pylons
                if (self.already_pending(UnitTypeId.PYLON) == 0):
                    if (self.can_afford(UnitTypeId.PYLON)):
                        await self.build(UnitTypeId.PYLON, near=random.choice(self.townhalls))
                        found_something = True

            if (not found_something):
                for nexus in self.townhalls:
                    # Get worker count for this nexus
                    # TODO: nexus.assigned_harvesters?
                    worker_count = len(self.workers.closer_than(10, nexus))
                    if (worker_count < 22):  # 16+3+3
                        if (nexus.is_idle and self.can_afford(UnitTypeId.PROBE)):
                            nexus.train(UnitTypeId.PROBE)
                            found_something = True

                    # Have we built enough assimilators?
                    for geyser in self.vespene_geyser.closer_than(10, nexus):
                        if (not self.can_afford(UnitTypeId.ASSIMILATOR)):
                            break
                        if (not self.structures(UnitTypeId.ASSIMILATOR).closer_than(2.0, geyser).exists):
                            await self.build(UnitTypeId.ASSIMILATOR, geyser)
                            found_something = True

            if (not found_something):
                if (self.already_pending(UnitTypeId.NEXUS) == 0 and self.can_afford(UnitTypeId.NEXUS)):
                    await self.expand_now()

        except Exception as e:
            print(e)

    def explore(self, iteration: int):
        # TODO: Implement an exploration policy

        # TODO: Instead of having to pass `iteration`, I think I can just use self.client.game_step
        # TODO: This can definitely be improved
        # Are there any idle probes?
        try:
            self.last_sent
        except:
            self.last_sent = 0

        # If self.last_sent doesn't exist yet
        if ((iteration - self.last_sent) > 200):
            try:
                probe = None
                if (self.units(UnitTypeId.PROBE).idle.exists):
                    # pick one of these randomly
                    probe = random.choice(
                        self.units(UnitTypeId.PROBE).idle)
                else:
                    probe = random.choice(self.units(UnitTypeId.PROBE))

                if (probe):
                    # Send a probe towards enemy base
                    probe.attack(self.enemy_start_locations[0])
                    self.last_sent = iteration

            except Exception as e:
                pass

    def attack(self):
        try:
            # take all void rays and attack!
            for voidray in self.units(UnitTypeId.VOIDRAY).idle:
                # if we can attack:
                if self.enemy_units.closer_than(10, voidray):
                    voidray.attack(random.choice(
                        self.enemy_units.closer_than(10, voidray)))
                # if we can attack:
                elif self.enemy_structures.closer_than(10, voidray):
                    voidray.attack(random.choice(
                        self.enemy_structures.closer_than(10, voidray)))
                # any enemy units:
                elif self.enemy_units:
                    voidray.attack(random.choice(self.enemy_units))
                # any enemy structures:
                elif self.enemy_structures:
                    voidray.attack(random.choice(self.enemy_structures))
                # if we can attack:
                elif self.enemy_start_locations:
                    voidray.attack(self.enemy_start_locations[0])

        except Exception as e:
            print(e)

    def make_map(self):
        map = np.zeros(
            (self.game_info.map_size[0], self.game_info.map_size[1], 3), dtype=np.uint8)

        # Draw the minerals
        for mineral in self.mineral_field:
            pos = mineral.position
            c = [175, 255, 255]
            fraction = mineral.mineral_contents / 1800
            if mineral.is_visible:
                # print(mineral.mineral_contents)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]
            else:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [20, 75, 50]

        # Draw the enemy start location
        for enemy_start_location in self.enemy_start_locations:
            pos = enemy_start_location
            c = [0, 0, 255]
            map[math.ceil(pos.y)][math.ceil(pos.x)] = c

        # Draw the enemy units
        for enemy_unit in self.enemy_units:
            pos = enemy_unit.position
            c = [100, 0, 255]
            # Get unit health fraction
            fraction = enemy_unit.health / \
                (enemy_unit.health_max if enemy_unit.health_max > 0 else 0.0001)
            map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                int(fraction * i) for i in c]

        # Draw the enemy structures
        for enemy_structure in self.enemy_structures:
            pos = enemy_structure.position
            c = [0, 100, 255]
            # Get structure health fraction
            fraction = enemy_structure.health / \
                (enemy_structure.health_max if enemy_structure.health_max > 0 else 0.0001)
            map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                int(fraction * i) for i in c]

        # Draw our structures
        for our_structure in self.structures:
            if (our_structure.type_id == UnitTypeId.NEXUS):
                pos = our_structure.position
                c = [255, 255, 175]
                # Get structure health fraction
                fraction = our_structure.health / \
                    (our_structure.health_max if our_structure.health_max > 0 else 0.0001)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]

            else:
                pos = our_structure.position
                c = [0, 255, 175]
                # Get structure health fraction
                fraction = our_structure.health / \
                    (our_structure.health_max if our_structure.health_max > 0 else 0.0001)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]

        # Draw the vespene geysers
        for vespene in self.vespene_geyser:
            # Draw these after buildings, since assimilators go over them.
            # tried to denote some way that assimilator was on top, couldnt
            # come up with anything. Tried by positions, but the positions arent identical. ie:
            # vesp position: (50.5, 63.5)
            # bldg positions: [(64.369873046875, 58.982421875), (52.85693359375, 51.593505859375),...]
            pos = vespene.position
            c = [255, 175, 255]
            fraction = vespene.vespene_contents / 2250

            if vespene.is_visible:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]
            else:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [50, 20, 75]

        # Draw our units
        for our_unit in self.units:
            if (our_unit.type_id == UnitTypeId.VOIDRAY):
                pos = our_unit.position
                c = [255, 75, 75]
                # Get health
                fraction = our_unit.health / \
                    (our_unit.health_max if our_unit.health_max > 0 else 0.0001)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]

            else:
                pos = our_unit.position
                c = [175, 255, 0]
                # Get health
                fraction = our_unit.health / \
                    (our_unit.health_max if our_unit.health_max > 0 else 0.0001)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction * i) for i in c]

        # Show resized and horizontally flipped map
        cv2.imshow('map', cv2.flip(cv2.resize(map, None, fx=4,
                   fy=4, interpolation=cv2.INTER_NEAREST), 0))
        cv2.waitKey(1)

        return map


if __name__ == "__main__":
    result = run_game(
        maps.get("AcropolisLE"),
        # List of players
        [Bot(Race.Protoss, SC2Bot()),
         Computer(Race.Zerg, Difficulty.Hard)],
        # If this is true, then the agent has a limited amount of time to make a decision
        realtime=False,
        # disable_fog=True
    )

    if (str(result) == "Result.Victory"):
        reward = 500
    else:
        reward = -500

    with open("results.txt", "a") as f:
        f.write(f"{result}\n")

    map = np.zeros((176, 184, 3), dtype=np.uint8)
    observation = map
    # Empty action waiting for the next one!
    data = {"state": map, "reward": reward, "action": None, "terminated": True}
    with open('state_rwd_action.pkl', 'wb') as f:
        pickle.dump(data, f)

    cv2.destroyAllWindows()
    cv2.waitKey(1)
    time.sleep(3)
    sys.exit()
