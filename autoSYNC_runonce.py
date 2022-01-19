#!/usr/bin/python3 -i

import meraki
import copy
import os
import pickle

from meraki import aio
#from mNetlib import *  
from mNetClone_aio import * #new library

import tagHelper2_aio
import time
import get_keys as g


async def main():
    async with meraki.aio.AsyncDashboardAPI(
                api_key=g.get_api_key(),
                base_url="https://api.meraki.com/api/v1",
                output_log=True,
                log_file_prefix=os.path.basename(__file__)[:-3],
                log_path='Logs/',
                print_console=False,
        ) as aiomeraki:
        


            print()
            print("What tag would you like to source from? Default is 'golden' if left blank")
            tag_golden = input("TAG:")
            if len(tag_golden) == 0:
                tag_golden  = "golden"

            print()
            print("What tag would you like to target? Default is 'autoSYNC' if left blank")
            tag_target = input("TAG:")
            if len(tag_target) == 0:
                tag_target  = "autoSYNC"


            print(f'TAG Target[{tag_target}] Golden[{tag_golden}]')

            orgs = await aiomeraki.organizations.getOrganizations()
            orgs_whitelist = [] 

            for o in orgs:
                orgs_whitelist.append(o['id'])
            print(orgs_whitelist)

            orgs_whitelist = ['121177', '577586652210266696', '577586652210266697'] #, '749286388003766274']


            #th = tagHelper2.tagHelper(db, tag_target, tag_golden, orgs_whitelist)
            th = tagHelper2_aio.tagHelper(aiomeraki, tag_target, tag_golden, orgs_whitelist)
            await th.sync()
            orgs = th.orgs #get a lit of orgs

            if th.golden_net == None:
                print(f'Exiting because no golden network was found. Golden master needs both the TARGET and the GOLDEN tag applied')
                exit()

            if not len(th.nets) >= 2:
                print(f'Needs at least two networks to clone/copy!')
                exit()

            th.show()

            golden_netid = th.golden_net['id']
            golden_net = await mNET(aiomeraki, golden_netid, True).loadCache()

            last_net = None

            WRITE = False
            ans = input('ARE YOU SURE? Type "ACCEPT MY FATE" to run: ')
            if ans == "ACCEPT MY FATE":
                WRITE = True

            if not WRITE: 
                print("EXITING!!!")
                return
                

            print("Running in 10 seconds....")
            sleep(9)
            print("Running in 1 second.....")
            sleep(1)

            for n in th.nets:
                if th.nets[n]['id'] == th.golden_net['id']:
                    continue
                mnet_test = await mNET(aiomeraki, n, True).loadCache()
                last_net = mnet_test
                await mnet_test.cloneFrom(golden_net)
                

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main()) 
