import os
import pickle
import subprocess
import numpy as np

import gymnasium as gym
import numpy as np
from gymnasium import spaces

IDLE_WORKER_NEXUS_THRESHOLD = 5
PHOTON_CANNONS_PER_FORGE = 3
MIN_PYLONS = 5
MIN_VOIDRAYS = 10
MAX_PROBES_PER_NEXUS = 16


class SC2Env(gym.Env):
    # TODO: Change?
    metadata = {"render_modes": ["human"], "render_fps": 30}

    def __init__(self):
        super(SC2Env, self).__init__()

        N_DISCRETE_ACTIONS = 6
        N_CHANNELS = 3  # RGB
        # Size of the map. Check from (not here) self.game_info.map_size
        # WIDTH, HEIGHT = 224, 224
        self.WIDTH, self.HEIGHT = 176, 184
        self.MAP_SHAPE = (self.WIDTH, self.HEIGHT, N_CHANNELS)
        self.action_space = spaces.Discrete(N_DISCRETE_ACTIONS)
        self.observation_space = spaces.Box(
            low=0, high=255, shape=self.MAP_SHAPE, dtype=np.uint8)

    def step(self, action):
        # Make observation: Wait for the action file to be modified
        wait_for_action = True
        while wait_for_action:
            # print("waiting for action")
            try:
                with open('state_rwd_action.pkl', 'rb') as f:
                    state_rwd_action = pickle.load(f)

                    if (state_rwd_action['action'] is not None):
                        # print("No action yet")
                        wait_for_action = True
                    else:
                        # print("Needs action")
                        wait_for_action = False
                        state_rwd_action['action'] = action
                        with open('state_rwd_action.pkl', 'wb') as f:
                            pickle.dump(state_rwd_action, f)
            except Exception as e:
                # print(str(e))
                pass

        # Waits for the new state to return (map and reward) (no new action yet)
        wait_for_state = True
        while wait_for_state:
            try:
                # File not empty => There is at least 1 state/action entry
                if (os.path.getsize('state_rwd_action.pkl') > 0):
                    with open('state_rwd_action.pkl', 'rb') as f:
                        state_rwd_action = pickle.load(f)
                        if state_rwd_action['action'] is None:
                            # print("No state yet")
                            wait_for_state = True
                        else:
                            # print("Got state state")
                            state = state_rwd_action['state']
                            self.reward = state_rwd_action['reward']
                            self.terminated = state_rwd_action['terminated']
                            wait_for_state = False

            except Exception as e:
                wait_for_state = True
                map = np.zeros(self.MAP_SHAPE, dtype=np.uint8)
                self.observation = map
                # If still failing, input an ACTION, 3 (scout)
                # Empty action waiting for the next one!
                data = {"state": map, "reward": 0,
                        "action": 3, "terminated": False}
                with open('state_rwd_action.pkl', 'wb') as f:
                    pickle.dump(data, f)

                state = map
                self.reward = 0
                self.terminated = False
                action = 3

        # self.info is always empty
        self.observation = state
        return self.observation, self.reward, self.terminated, self.truncated, self.info

    def reset(self, seed=None, options=None):
        self.terminated = False
        self.truncated = False
        self.reward = 0
        self.info = {}

        print("**************RESETTING ENVIRONMENT**************")
        map = np.zeros(self.MAP_SHAPE, dtype=np.uint8)
        self.observation = map

        # Empty action waiting for the next one!
        data = {"state": map, "reward": 0, "action": None, "terminated": False}
        with open('state_rwd_action.pkl', 'wb') as f:
            pickle.dump(data, f)

        # Run `sc2bot_v1.py` non-blocking
        # subprocess.Popen(["python", "sc2bot_v1.py"])
        subprocess.Popen([".\\.venv\\Scripts\\activate", "&&",
                         "python", "sc2bot_v1.py"], shell=True)
        return self.observation, self.info
