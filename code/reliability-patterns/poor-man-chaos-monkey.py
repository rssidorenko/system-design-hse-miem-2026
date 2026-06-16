# Специальная утилита, которая демонстрирует псевдо-хаос-тестирование. Если хочется жести см. сюда: https://github.com/dastergon/awesome-chaos-engineering?tab=readme-ov-file 

import time
import random
import subprocess
import logging

TARGET_CONTAINER = "unstable-backend" 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def chaos_loop():
    logging.info(f"chaos monkey is coming for '{TARGET_CONTAINER}'...")
    
    while True:
        # Мартышка спит и ничего не делает 5-10 секунд (нормальная работа)
        sleep_time = random.randint(5, 10)
        time.sleep(sleep_time)
        
        action = random.choice(["freeze", "kill", "nothing"])
        
        if action == "freeze":
            logging.info("monkey FREEZE container!")
            run_cmd(f"docker pause {TARGET_CONTAINER}")
            
            time.sleep(5) 
            
            run_cmd(f"docker unpause {TARGET_CONTAINER}")
            logging.info("monkey UNFREEZE container")

            time.sleep(5)
            
        elif action == "kill":
            logging.info("monkey Kill container!")
            run_cmd(f"docker restart {TARGET_CONTAINER}")
            logging.info("container rebooting...")
            
            time.sleep(5)
            
        elif action == "nothing":
            logging.info("system is stable druzhishe")

if __name__ == "__main__":
    try:
        chaos_loop()
    except KeyboardInterrupt:
        run_cmd(f"docker unpause {TARGET_CONTAINER}")
        print("\nbye-bye")