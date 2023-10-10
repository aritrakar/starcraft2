import math
import random
import numpy as np

import cv2
from sc2 import maps
from sc2.bot_ai import BotAI  # Parent class
from sc2.constants import UnitTypeId
from sc2.data import Difficulty, Race, Result
from sc2.main import run_game
# Bot is what we will use to create our own bot
# Computer is pre-automated
from sc2.player import Bot, Computer
from sc2.position import Point2


# PROBLEMS:
# 1. Photon cannons not being built
# 2. Supply depots not being built
# 3. Too many nexus being built
# 4. Additional stargates, etc. not being built
# 5. No exploration as such

class AriBot(BotAI):
    def __init__(self):
        self.ITERATIONS_PER_MINUTE = 165  # Not sure how this was defined
        self.STARGATES_PER_NEXUS = 5
        self.IDLE_WORKER_NEXUS_THRESHOLD = 5
        self.PHOTON_CANNONS_PER_FORGE = 3
        self.MIN_PYLONS = 5
        self.MIN_VOIDRAYS = 10
        self.MAX_PROBES_PER_NEXUS = 16
        self.CLOSEST_PHOTON_CANNON = 15

    # async def on_start(self):
    #     # Disable map
    #     # self.client.map
    #     return super().on_start()

    async def on_step(self, iteration):
        print(self.game_info.map_size)
        TO_LOG = [UnitTypeId.PROBE, UnitTypeId.NEXUS, UnitTypeId.PYLON, UnitTypeId.PHOTONCANNON, UnitTypeId.GATEWAY,
                  UnitTypeId.CYBERNETICSCORE, UnitTypeId.STARGATE, UnitTypeId.ASSIMILATOR, UnitTypeId.VOIDRAY, UnitTypeId.SUPPLYDEPOT]
        res = str(iteration) + ". "
        for unit in TO_LOG:
            res += f"{unit.name}: {self.units(unit).amount} "
        print(res)

        if (not self.townhalls):
            await self.expand()

        # TODO: Check if opponent wants to surrender
        # Need to use some sort of heuristic because python-sc2 doesn't support this yet.

        if (self.client.game_step > 0 and not self.townhalls.ready):
            # Attack with all workers if we don't have any nexuses left,
            # attack-move on enemy spawn so that probes auto attack on the way
            for vr in self.units(UnitTypeId.VOIDRAY):
                if (vr.is_idle):
                    vr.attack(self.enemy_start_locations[0])
            return

        await self.build_workers()
        await self.explore()
        await self.distribute_workers()
        await self.build_pylons()
        await self.harvest_vespene()
        await self.build_defense_structures()
        await self.build_defense_units()
        await self.expand()
        self.attack()

        self.make_map()

    async def expand(self):
        '''Expand to a new base.'''
        # if (not self.already_pending(UnitTypeId.NEXUS) and self.can_afford(UnitTypeId.NEXUS)):
        #     await self.expand_now()
        if (self.units(UnitTypeId.NEXUS).amount < (self.client.game_step / self.ITERATIONS_PER_MINUTE) and
                self.can_afford(UnitTypeId.NEXUS)):
            await self.expand_now()

    async def build_workers(self):
        '''Build workers until we have the max amount per nexus.'''
        for nexus in self.townhalls.ready.idle:
            if (nexus.assigned_harvesters < nexus.ideal_harvesters):
                if (self.can_afford(UnitTypeId.PROBE)):
                    nexus.train(UnitTypeId.PROBE)
            else:
                # Build a supply depot if we're at capacity
                # if (self.supply_left < 5 and self.supply_cap < 200):
                await self.build_supply_depots(nexus, 3)
                await self.build_pylons()
                await self.expand()

            # Start mining
            # for worker in self.workers.idle:
            #     worker.gather(self.mineral_field.closest_to(worker))

    async def build_supply_depots(self, nexus: UnitTypeId.NEXUS, num_depots: int):
        '''Build supply depots if we are low on supply.'''
        for _ in range(num_depots):
            if (self.can_afford(UnitTypeId.SUPPLYDEPOT)):
                await self.build(UnitTypeId.SUPPLYDEPOT, near=nexus)

    async def build_pylons(self):
        '''Build pylons if we are low on supply, and a forge if we already have pylons.'''
        # TODO: Probably should change this?
        nexus = self.townhalls.ready.random
        if (not self.structures(UnitTypeId.PYLON) and not self.already_pending(UnitTypeId.PYLON)):
            if (self.can_afford(UnitTypeId.PYLON)):
                # Keep it near the Nexus for now
                await self.build(UnitTypeId.PYLON, near=nexus)

        elif (self.structures(UnitTypeId.PYLON).amount < self.MIN_PYLONS):
            if (self.can_afford(UnitTypeId.PYLON)):
                target_pylon = self.structures(UnitTypeId.PYLON).closest_to(
                    self.enemy_start_locations[0])
                position = target_pylon.position.towards(
                    self.enemy_start_locations[0], random.randrange(5, 15))  # 8, 15
                await self.build(UnitTypeId.PYLON, near=position)

        # If we have pylons, build forge (if we don't already have one)
            elif (not self.structures(UnitTypeId.FORGE)):
                if (self.can_afford(UnitTypeId.FORGE)):
                    await self.build(UnitTypeId.FORGE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

    async def harvest_vespene(self):
        for nexus in self.townhalls.ready:
            for vespene in self.vespene_geyser.closer_than(15.0, nexus):
                # Build an assimilator on top of the vespene if there isn't one already
                # TODO: How do I check if a vespene geyser has an assimilator on it?
                if (self.can_afford(UnitTypeId.ASSIMILATOR) and not self.already_pending(UnitTypeId.ASSIMILATOR)):
                    await self.build(UnitTypeId.ASSIMILATOR, vespene)

    async def build_defense_structures(self):
        '''Build photon cannons to defend the base.'''
        for nexus in self.townhalls.ready:
            # Check distance to the closest photon cannon
            closest = 1000  # Arbitrarily large number
            if (self.structures(UnitTypeId.PHOTONCANNON)):
                closest = nexus.position.distance_to(
                    self.structures(UnitTypeId.PHOTONCANNON).closest_to(nexus).position)

            # If it's too far and the necessary structures are built, build photon cannons
            if ((closest > self.CLOSEST_PHOTON_CANNON) and
                    self.structures(UnitTypeId.FORGE).ready):
                # if (self.structures(UnitTypeId.PHOTONCANNON)):
                # (self.structures(UnitTypeId.PHOTONCANNON).amount < self.PHOTON_CANNONS_PER_FORGE)

                if (not self.structures(UnitTypeId.PHOTONCANNON)):
                    # Build as many photon cannons as you can
                    for _ in self.PHOTON_CANNONS_PER_FORGE:
                        if (self.can_afford(UnitTypeId.PHOTONCANNON)):
                            # Find the closest ramp
                            ramp = self.get_closest_ramp(
                                nexus.position, self.game_info.map_center)

                            # Build a photon cannon near the ramp
                            if (ramp is not None):
                                position = ramp.towards(nexus.position, 5)
                                await self.build(UnitTypeId.PHOTONCANNON, near=position)

    async def get_closest_ramp(self, start, end) -> Point2:
        '''Find the closest ramp to the given start and end positions.'''
        path = await self._client.query_pathing(start, end)
        if (path is None):
            return None

        # Find the closest ramp to the end position
        ramps = self.game_info.map_ramps
        closest_ramp = None
        closest_distance = None
        for ramp in ramps:
            distance = ramp.top_center.distance_to(end)
            if (closest_distance is None or distance < closest_distance):
                closest_ramp = ramp
                closest_distance = distance

        return closest_ramp

    async def build_defense_units(self):
        '''Build void rays to defend the base.'''
        for nexus in self.townhalls.ready:
            # Flaw in logic here. This only works for the FIRST nexus.
            # How can I make this work for all nexuses?
            # Check for presence of buildings within a certain radius.
            if (not self.structures(UnitTypeId.GATEWAY)):
                if (self.can_afford(UnitTypeId.GATEWAY)):
                    await self.build(UnitTypeId.GATEWAY, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

            elif (not self.structures(UnitTypeId.CYBERNETICSCORE)):
                if (self.can_afford(UnitTypeId.CYBERNETICSCORE)):
                    await self.build(UnitTypeId.CYBERNETICSCORE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

            # elif (not self.structures(UnitTypeId.STARGATE)):
            elif (not self.structures(UnitTypeId.STARGATE) or self.structures(UnitTypeId.STARGATE).amount < self.STARGATES_PER_NEXUS):
                if (self.can_afford(UnitTypeId.STARGATE)):
                    await self.build(UnitTypeId.STARGATE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

        # Build void rays if we have a stargate
        if (self.structures(UnitTypeId.STARGATE).ready):
            for sg in self.structures(UnitTypeId.STARGATE).ready.idle:
                if (self.can_afford(UnitTypeId.VOIDRAY)):
                    sg.train(UnitTypeId.VOIDRAY)

    def attack(self):
        # Attack with Void Rays
        # If you've seen an enemy, attack them
        # Otherwise, attack any seen enemy structures
        # Otherwise, attack the enemy start location
        if (self.units(UnitTypeId.VOIDRAY).amount >= (self.MIN_VOIDRAYS // 2)):
            # TODO: Make Race-specific decisions
            # TODO: Use better strategies
            if (self.enemy_units):
                for vr in self.units(UnitTypeId.VOIDRAY).idle:
                    # Attack the closest enemy unit
                    vr.attack(self.enemy_units.closest_to(vr))

            elif (self.enemy_structures):
                for vr in self.units(UnitTypeId.VOIDRAY).idle:
                    # Attack the closest enemy structure
                    vr.attack(self.enemy_structures.closest_to(vr))

            else:
                for vr in self.units(UnitTypeId.VOIDRAY).idle:
                    # Attack the enemy start location
                    vr.attack(self.enemy_start_locations[0])

    async def explore(self):
        '''Explore the map to discover new areas and enemy bases.'''
        if (self.units(UnitTypeId.PROBE).amount > 0):
            probe = self.units(UnitTypeId.PROBE).random
            if (probe.is_idle):
                # Random exploration
                if (self.time % 30 == 0):
                    location = await self.get_random_location()
                    await probe.move(location)

                # Targeted exploration
                elif (self.time % 30 == 15):
                    ramp = await self.get_closest_ramp(probe.position)
                    if (ramp is not None):
                        await probe.move(ramp)

    def get_random_location(self):
        '''Get a random location on the map.'''
        x = random.randint(0, self.game_info.map_size[0])
        y = random.randint(0, self.game_info.map_size[1])
        return Point2((x, y))

    def make_map(self):
        map = np.zeros(
            (self.game_info.map_size[0], self.game_info.map_size[1], 3), dtype=np.uint8)

        # draw the minerals:
        for mineral in self.mineral_field:
            pos = mineral.position
            c = [175, 255, 255]
            fraction = mineral.mineral_contents / 1800
            if mineral.is_visible:
                # print(mineral.mineral_contents)
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]
            else:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [20, 75, 50]

        # draw the enemy start location:
        for enemy_start_location in self.enemy_start_locations:
            pos = enemy_start_location
            c = [0, 0, 255]
            map[math.ceil(pos.y)][math.ceil(pos.x)] = c

        # draw the enemy units:
        for enemy_unit in self.enemy_units:
            pos = enemy_unit.position
            c = [100, 0, 255]
            # get unit health fraction:
            fraction = enemy_unit.health / \
                enemy_unit.health_max if enemy_unit.health_max > 0 else 0.0001
            map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                int(fraction*i) for i in c]

        # draw the enemy structures:
        for enemy_structure in self.enemy_structures:
            pos = enemy_structure.position
            c = [0, 100, 255]
            # get structure health fraction:
            fraction = enemy_structure.health / \
                enemy_structure.health_max if enemy_structure.health_max > 0 else 0.0001
            map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                int(fraction*i) for i in c]

        # draw our structures:
        for our_structure in self.structures:
            # if it's a nexus:
            if our_structure.type_id == UnitTypeId.NEXUS:
                pos = our_structure.position
                c = [255, 255, 175]
                # get structure health fraction:
                fraction = our_structure.health / \
                    our_structure.health_max if our_structure.health_max > 0 else 0.0001
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]

            else:
                pos = our_structure.position
                c = [0, 255, 175]
                # get structure health fraction:
                fraction = our_structure.health / \
                    our_structure.health_max if our_structure.health_max > 0 else 0.0001
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]

        # draw the vespene geysers:
        for vespene in self.vespene_geyser:
            # draw these after buildings, since assimilators go over them.
            # tried to denote some way that assimilator was on top, couldnt
            # come up with anything. Tried by positions, but the positions arent identical. ie:
            # vesp position: (50.5, 63.5)
            # bldg positions: [(64.369873046875, 58.982421875), (52.85693359375, 51.593505859375),...]
            pos = vespene.position
            c = [255, 175, 255]
            fraction = vespene.vespene_contents / 2250

            if vespene.is_visible:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]
            else:
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [50, 20, 75]

        # draw our units:
        for our_unit in self.units:
            # if it is a voidray:
            if our_unit.type_id == UnitTypeId.VOIDRAY:
                pos = our_unit.position
                c = [255, 75, 75]
                # get health:
                fraction = our_unit.health / our_unit.health_max if our_unit.health_max > 0 else 0.0001
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]

            else:
                pos = our_unit.position
                c = [175, 255, 0]
                # get health:
                fraction = our_unit.health / our_unit.health_max if our_unit.health_max > 0 else 0.0001
                map[math.ceil(pos.y)][math.ceil(pos.x)] = [
                    int(fraction*i) for i in c]

        # show map with opencv, resized to be larger:
        # horizontal flip:

        cv2.imshow('map', cv2.flip(cv2.resize(map, None, fx=4,
                   fy=4, interpolation=cv2.INTER_NEAREST), 0))
        cv2.waitKey(1)

    def on_end(self, game_result: Result):
        print("Iterations: ", self.client.game_step)
        return super().on_end(game_result)


if __name__ == "__main__":
    run_game(
        maps.get("AcropolisLE"),
        # List of players
        [Bot(Race.Protoss, AriBot()),
         Computer(Race.Zerg, Difficulty.Hard)],
        # If this is true, then the agent has a limited amount of time to make a decision
        realtime=False,
        # disable_fog=True,
    )
