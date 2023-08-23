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
from sc2.unit import Unit

IDLE_WORKER_NEXUS_THRESHOLD = 5
PHOTON_CANNONS_PER_FORGE = 3
MIN_PYLONS = 5
MIN_VOIDRAYS = 10
MAX_PROBES_PER_NEXUS = 16


class AriBot(BotAI):
    # async def on_start(self):
    #     # Disable map
    #     # self.client.map
    #     return super().on_start()

    async def on_step(self, iteration):
        # Main logic goes here
        # print("Iteration: ", iteration)

        TO_LOG = [UnitTypeId.PROBE, UnitTypeId.NEXUS, UnitTypeId.PYLON, UnitTypeId.PHOTONCANNON, UnitTypeId.GATEWAY,
                  UnitTypeId.CYBERNETICSCORE, UnitTypeId.STARGATE, UnitTypeId.ASSIMILATOR, UnitTypeId.VOIDRAY, UnitTypeId.SUPPLYDEPOT]
        res = ""
        for unit in TO_LOG:
            res += f"{unit.name}: {self.units(unit).amount} "
        print(res)

        # print("Probes: ", self.units(UnitTypeId.PROBE).amount, "Nexuses: ", self.townhalls.amount, "Pylons: ", self.structures(UnitTypeId.PYLON).amount, "Cannons: ", self.structures(UnitTypeId.PHOTONCANNON).amount, "Gateways: ", self.structures(UnitTypeId.GATEWAY).amount, "Cores: ", self.structures(
        # UnitTypeId.CYBERNETICSCORE).amount, "Stargates: ", self.structures(UnitTypeId.STARGATE).amount, "Assimilators: ", self.structures(UnitTypeId.ASSIMILATOR).amount, "Void Rays: ", self.units(UnitTypeId.VOIDRAY).amount, "Workers: ", self.workers.amount, "Minerals: ", self.minerals, "Vespene: ", self.vespene)

        if (self.client.game_step > 0 and not self.townhalls.ready):
            # Attack with all workers if we don't have any nexuses left, attack-move on enemy spawn (doesn't work on 4 player map) so that probes auto attack on the way
            for worker in self.workers:
                worker.attack(self.enemy_start_locations[0])
            return

        # TODO: Check if opponent wants to surrender
        # Need to use some sort of heuristic because python-sc2 doesn't support this yet.

        # Redistribute workers (like this for now, but it's slow)
        await self.distribute_workers()

        # First, check for Nexuses
        if (self.townhalls):
            nexus = self.townhalls.random
            max_workers = (len(self.mineral_field.closer_than(
                10, nexus)) * 2) + (len(self.vespene_geyser.closer_than(15, nexus)) * 3)

            if ((self.structures(UnitTypeId.VOIDRAY).amount < MIN_VOIDRAYS) and self.can_afford(UnitTypeId.VOIDRAY) and self.structures(UnitTypeId.STARGATE).ready):
                for sg in self.structures(UnitTypeId.STARGATE).ready.idle:
                    sg.train(UnitTypeId.VOIDRAY)

            # If we have a nexus, build probes
            if (nexus.is_idle and self.can_afford(UnitTypeId.PROBE)):
                # max_workers = (len(self.mineral_field.closer_than(
                #     10, nexus)) * 2) + (len(self.vespene_geyser.closer_than(15, nexus)) * 3)

                # print("Max workers: ", max_workers,
                #       "Assigned workers: ", nexus.assigned_harvesters)
                # # If you've reached the nexus capacity, build a Supply Depot first
                # if (nexus.assigned_harvesters > max_workers):
                #     if (self.can_afford(UnitTypeId.SUPPLYDEPOT)):
                #         await self.build(UnitTypeId.SUPPLYDEPOT, near=nexus)

                # Now build a probe
                nexus.train(UnitTypeId.PROBE)

            # elif (not self.already_pending(UnitTypeId.SUPPLYDEPOT)):
            #     print("Max workers: ", max_workers,
            #           "Assigned workers: ", nexus.assigned_harvesters)
            #     # If you've reached the nexus capacity, build a Supply Depot first
            #     if (nexus.assigned_harvesters > max_workers):
            #         if (self.can_afford(UnitTypeId.SUPPLYDEPOT)):
            #             await self.build(UnitTypeId.SUPPLYDEPOT, near=nexus)

            # If we have probes, build pylons
            elif (not self.structures(UnitTypeId.PYLON) and not self.already_pending(UnitTypeId.PYLON)):
                if (self.can_afford(UnitTypeId.PYLON)):
                    # Keep it near the Nexus for now
                    await self.build(UnitTypeId.PYLON, near=nexus)

            elif (self.structures(UnitTypeId.PYLON).amount < MIN_PYLONS):
                if (self.can_afford(UnitTypeId.PYLON)):
                    target_pylon = self.structures(UnitTypeId.PYLON).closest_to(
                        self.enemy_start_locations[0])
                    position = target_pylon.position.towards(
                        self.enemy_start_locations[0], random.randrange(5, 15))  # 8, 15
                    # await self.build(UnitTypeId.PYLON, near=target_pylon.position.towards(self.game_info.map_center, 5))
                    await self.build(UnitTypeId.PYLON, near=position)

            # For Vespene Gas, we need an Assimilator
            elif (self.structures(UnitTypeId.ASSIMILATOR).amount < 2):
                vespenes = self.vespene_geyser.closer_than(15.0, nexus)
                for vespene in vespenes:
                    # Build an assimilator on top of the vespene
                    if (self.can_afford(UnitTypeId.ASSIMILATOR) and not self.already_pending(UnitTypeId.ASSIMILATOR)):
                        await self.build(UnitTypeId.ASSIMILATOR, vespene)

            # If we have pylons, build forge (if we don't already have one)
            elif (not self.structures(UnitTypeId.FORGE)):
                if (self.can_afford(UnitTypeId.FORGE)):
                    await self.build(UnitTypeId.FORGE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

            # Now build photon cannons to protect the base
            elif (self.structures(UnitTypeId.FORGE).ready and self.structures(UnitTypeId.PHOTONCANNON).amount < PHOTON_CANNONS_PER_FORGE):
                if (self.can_afford(UnitTypeId.PHOTONCANNON)):
                    # Try to find the ramp
                    position = nexus.position.towards(
                        self.game_info.map_center, random.randrange(3, 7))
                    await self.build(UnitTypeId.PHOTONCANNON, near=position)

            # Make Void Rays (for now)
            # Need Gateway, Cybernetics Core, Stargate, and Vespene Gas
            elif (not self.structures(UnitTypeId.GATEWAY)):
                if (self.can_afford(UnitTypeId.GATEWAY)):
                    await self.build(UnitTypeId.GATEWAY, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

            elif (not self.structures(UnitTypeId.CYBERNETICSCORE)):
                if (self.can_afford(UnitTypeId.CYBERNETICSCORE)):
                    await self.build(UnitTypeId.CYBERNETICSCORE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

            elif (not self.structures(UnitTypeId.STARGATE)):
                if (self.can_afford(UnitTypeId.STARGATE)):
                    await self.build(UnitTypeId.STARGATE, near=self.structures(UnitTypeId.PYLON).closest_to(nexus))

        else:
            if (self.can_afford(UnitTypeId.NEXUS)):
                # If we don't have a nexus, build one
                # await self.build(UnitTypeId.NEXUS, near=self.start_location)
                await self.expand_now()

        # Attack with Void Rays
        # If you've seen an enemy, attack them
        # Otherwise, attack any seen enemy structures
        # Otherwise, attack the enemy start location
        if (self.units(UnitTypeId.VOIDRAY).amount >= (MIN_VOIDRAYS // 2)):
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

        # Check for idle workers
        # NOTE: I'd call distribute_workers() here, but it's quite slow
        # apparently when the number of workers grows
        # for worker in self.workers.idle:
        #     # If you're too far from a Nexus, build one close to you
        #     if (worker.distance_to(self.townhalls.closest_to(worker)) > IDLE_WORKER_NEXUS_THRESHOLD):
        #         # await self.build(UnitTypeId.NEXUS, near=worker)
        #         if (self.can_afford(UnitTypeId.NEXUS) and not self.already_pending(UnitTypeId.NEXUS)):
        #             # await self.build(UnitTypeId.NEXUS, near=self.start_location)
        #             await self.expand_now()
        #     # Start mining
        #     worker.gather(self.mineral_field.closest_to(worker))

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

    async def on_unit_created(self, unit: Unit):
        if (unit.type_id == UnitTypeId.PROBE):
            # Send the probe to mine
            pass
        elif (unit.type_id == UnitTypeId.VOIDRAY):
            # Send the void ray to attack
            pass

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
        disable_fog=True,
    )
