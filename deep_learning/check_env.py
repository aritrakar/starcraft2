from stable_baselines3.common.env_checker import check_env
from env import SC2Env

env = SC2Env()

# It will check your custom environment and output additional warnings if needed
check_env(env)
