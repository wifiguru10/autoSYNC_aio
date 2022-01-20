#!/usr/bin/python3

### AutoSYNC v2 by Nico Darrow

### Description: 
#


import meraki.aio
from datetime import datetime
from time import *
import copy
import sys,os
import asyncio
from mNetClone_aio import *
from bcolors import bcolors
import tagHelper2_aio
import changelogHelper_aio
import configparser
import get_keys as g


#Defaults.... get overriden by autoSYNC.cfg
orgs_whitelist = [] 
WRITE = True
tag_target = ''
tag_golden = ''
TAGS = []
cfg = {}
newNets = []

def loadCFG(db,filename):

    if not os.path.exists(filename):
        print(f'{bc.FAIL}Config file [{filename}] is not found, please copy "autoSYNC.cfg.default" to "autoSYNC.cfg", edit and try running again{bc.ENDC}')
        print()
        sys.exit()

    print("LOADING CONFIG")
    config = configparser.ConfigParser()
    config.read(filename)

    cfg['filename'] = filename

    if 'true' in config['autoSYNC']['LOOP'].lower():
        cfg['LOOP'] = True
    else:
        cfg['LOOP'] = False
    
    if "LOOP_LIMIT" in config['autoSYNC']:
        cfg['LOOP_LIMIT'] = config['autoSYNC']['LOOP_LIMIT']
    else:
        cfg['LOOP_LIMIT'] = 0 #unlimited

    if 'true' in config['autoSYNC']['WRITE'].lower(): 
        cfg['WRITE'] = True
    else: 
        cfg['WRITE'] = False

    if 'true' in config['autoSYNC']['ALL_ORGS'].lower(): 
        orgs_whitelist = []
        cfg['whitelist'] = []
    else:  
        orgs_whitelist = config['autoSYNC']['Orgs'].replace(' ','').split(',')
        cfg['whitelist'] = config['autoSYNC']['Orgs'].replace(' ','').split(',')


    fields = ['SYNC_MR', 'SYNC_MS', 'SYNC_MX', 'SYNC_MG']
    for f in fields:
        if 'true' in config['autoSYNC'][f].lower():
            cfg[f] = True
        else: cfg[f] = False

    if 'true' in config['autoSYNC']['PAUSE_ON_FIRST_LOOP'].lower():
        cfg['PAUSE_OFL'] = True
    else:
        cfg['PAUSE_OFL'] = False


    cfg['tag_target'] = config['TAG']['TARGET']
    cfg['tag_golden'] = config['TAG']['GOLDEN']


#    cfg['adminEmails'] = config['ChangeLog']['emails'].replace(' ','').lower().split(',')
    

    return cfg


async def loadMNET(db, cfg, mNets, thn):
    if not thn in mNets:
        if not WRITE: print(f'WRITE IS FALSE!!!')
        mNets[thn] = await mNET(db, thn, cfg, WRITE).loadCache()
    return thn

async def main():
    # client_query() # this queries current org and all client information and builds database
    # exit()

    # Fire up Meraki API and build DB's
   
    log_dir = os.path.join(os.getcwd(), "Logs/")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    #db = meraki.DashboardAPI(api_key=g.get_api_key(), base_url='https://api.meraki.com/api/v1/', print_console=False, output_log=True, log_file_prefix=os.path.basename(__file__)[:-3], log_path='Logs/',) 
    async with meraki.aio.AsyncDashboardAPI(
            api_key=g.get_api_key(),
            base_url="https://api.meraki.com/api/v1",
            output_log=True,
            log_file_prefix=os.path.basename(__file__)[:-3],
            log_path='Logs/',
            maximum_concurrent_requests=10,
            maximum_retries= 100,
            wait_on_rate_limit=True,
            print_console=False,
    ) as aiomeraki:
        configFile = 'autoSYNC.cfg'
        cfg = loadCFG(aiomeraki,configFile)

        th_array = []
        tag_target = cfg['tag_target']
        tag_golden = cfg['tag_golden']
    #    adminEmails = cfg['adminEmails']
        orgs_whitelist = cfg['whitelist']
        WRITE = cfg['WRITE']
        

        th = tagHelper2_aio.tagHelper(aiomeraki, tag_target, tag_golden, orgs_whitelist)
        await th.sync()
        orgs = th.orgs #get a lit of orgs
        
        #Master ChangeLog Helper
        clh = changelogHelper_aio.changelogHelper(aiomeraki, orgs)
        clh.ignoreAPI = False #make sure it'll trigger on API changes too, default is TRUE

        clh_clones = changelogHelper_aio.changelogHelper(aiomeraki, orgs)
        clh_clones.tag_target = tag_target #this sets the TAG so it'll detect additions of new networks during runtime
    
        
        loop = True #Set this to false to break loop
        
        mNets = {} #Dictionary of {'net_id': <mnet_obj>}
        master_netid = None
        mr_obj = [] #collect the networks
        #last_changes = []
        longest_loop = 0
        loop_count = 0
        oldNets = []
        newNets = [] #configured here because we'll remove the networkID as it gets loaded (so it can span multiple loops)
        while loop:
            print()
            print(f'\t{bcolors.HEADER}****************************{bcolors.FAIL}START LOOP{bcolors.HEADER}*****************************')
            print(bcolors.ENDC)
            startTime = time()

            if WRITE:
                print(f'{bcolors.OKGREEN}WRITE MODE[{bcolors.WARNING}ENABLED{bcolors.OKGREEN}]{bcolors.ENDC}')
            else:
                print(f'{bcolors.OKGREEN}WRITE MODE[{bcolors.WARNING}DISABLED{bcolors.OKGREEN}]{bcolors.ENDC}')

           
            # TagHelper sync networks
            oldNets = copy.deepcopy(th.nets)  #keep copy of old networks
            await th.sync() #taghelper, look for any new networks inscope
            for nn in th.nets:
                if not nn in oldNets:
                    newNets.append(nn)

            print(f'New Networks {newNets}')

            print()
            #Master Loader section
            netCount = 0
            startTime = time()

            loadMNETTasks = [loadMNET(aiomeraki, cfg, mNets, thn) for thn in th.nets]
            for task in asyncio.as_completed(loadMNETTasks):
                thn = await task
                netCount += 1
                if loop_count == 0:
                    print(f'{bc.WARNING}Network #{netCount} of [{len(th.nets)}] networks {bc.ENDC}')
                
                if not tag_golden in th.nets[thn]['tags']:
                    clh_clones.addNetwork(thn) #this goes into the CLONES bucket
                else:
                    if master_netid != thn:
                        master_netid = thn
                        clh.clearNetworks() #wipes out previous master
                        print(f'MASTER NETWORK change to netid[{thn}]')
                        clh.addNetwork(thn)

            endTime = time()
            print(f'It took {round(endTime-startTime,2)} seconds to load everything')
            
            print()
            #print(f'Master WL[{clh.watch_list}]')
            #rint(f'Clones WL[{clh_clones.watch_list}]')
            
            th.show() #show inscope networks/orgs
            if loop_count == 0 and cfg['PAUSE_OFL']:
                print()
                ans = input("FIRST LOOP PAUSE!!!  Press  <ENTER to continue or Ctrl-C to break>")
            
            #Cleanup for old mNET objects which have been removed from scope
            delList = []
            for mid in mNets: #cleanup
                if not mid in th.nets:
                    delList.append(mid)

            for mid in delList:
                mNets.pop(mid)
                print(f'Dropping network[{mid}] from mNets DB')
                clh_clones.delNetwork(mid)
                if master_netid == mid: #assuming the master is changed/removed
                    clh.delNetwork(mid) #remove it from changeloghelper 
                    master_netid = None

            if master_netid == None:
                print(f'Something went wrong, no master netid!!!')
                continue
                
            print()
            master_change = await clh.hasChange()
            clone_change = await clh_clones.hasChange()
            print(f'{bcolors.OKGREEN}Changes Master[{bcolors.WARNING}{master_change}{bcolors.OKGREEN}] Clone[{bcolors.WARNING}{clone_change}{bcolors.OKGREEN}]')
            print()

            print(f'{bcolors.OKGREEN}Loop Count[{bcolors.WARNING}{loop_count}{bcolors.OKGREEN}]')

            print()
            
            if len(newNets) > 0:
                clone_change = True
            if clone_change: #if there's a change to clones, run a short loop syncing just those networks
                print(f'{bcolors.FAIL}Change in a target Network Detected:{bcolors.Blink} Initializing Sync{bcolors.ENDC}')
                inscope_clones = clh_clones.changed_nets #gets list of networks changed
                newNetTasks = []
                doneNets = []
                for nn in newNets:
                    print(f'Cloning new network....')
                    #mNets[nn] = await mNET(aiomeraki, nn, cfg, WRITE).loadCache()
                    newNetTasks.append(mNets[nn].cloneFrom(mNets[master_netid]))
                    doneNets.append(nn)
                for task in asyncio.as_completed(newNetTasks):
                    await task

                for dn in doneNets: #clear out cloned networks in "newNets" so if next loop you won't reclone
                    print(f'Done processing {dn} network')
                    newNets.remove(dn)

                cloneTasks = []
                for ic in inscope_clones:
                    if not ic in mNets:
                        print(f'{bcolors.FAIL}New Network detected!!! NetID[{bcolors.WARNING}{ic}{bcolors.FAIL}]')
                        print(f'THIS NEVER SHOULD HAPPEN AT THIS POINT')
                        sys.exit(1)
                        mNets[ic] = await mNET(aiomeraki, ic, cfg, WRITE).loadCache()
                        await mNets[ic].cloneFrom(mNets[master_netid])
                    else:
                        
                        await mNets[ic].sync()
                        cloneTasks.append(mNets[ic].cloneFrom(mNets[master_netid]))
                    
                    for task in asyncio.as_completed(cloneTasks):
                        await task

            

            elif master_change or loop_count == 0:
                print(f'{bcolors.FAIL}Master change Detected:{bcolors.Blink} Syncing Networks{bcolors.ENDC}')
                mcCount = 0
                await mNets[master_netid].sync()
                avgTime = 0
                cloneTask = []
                for net in mNets:
                    if net == master_netid: continue
                    mcCount += 1
                    secondsGuess = avgTime * (len(th.nets)-1 - mcCount)
                    print(f'{bc.WARNING}Network #{mcCount} of [{len(th.nets)-1}] networks. AvgTime[{round(avgTime,1)}] seconds. Estimated [{round(secondsGuess/60,1)}] minutes left{bc.ENDC}')
                    startT = time()

                    #Niftly little workaround for finding "out of compliance" networks, if there's an exception or error, re-sync and try again
                    #tries = 1
                    #while tries > 0:
                        #try:
                    cloneTask.append(mNets[net].cloneFrom(mNets[master_netid]))
                    #asyncio.sleep(0.5)
                        #    tries = 0
                        #except:
                        #    #potentially something changed... 
                        #    print(f'\t{bc.FAIL}ERROR:{bc.OKBLUE} Something changed in network [{bc.WARNING}{mNets[net].name}{bc.OKBLUE}]. Re-Syncing network and trying again....{bc.ENDC}')
                        #    print(sys.exc_info())
                        #    await mNets[net].sync()
                        #tries -= 1
                    

                    endT = time()
                    dur = round(endT-startT,2)
                    if avgTime == 0:
                        avgTime = dur
                    else:
                        avgTime = ( avgTime + dur )/ 2
        
                for task in asyncio.as_completed(cloneTask):
                    await task #wait for all the cloned networks to finish processing
            else:
                print(f'{bc.OKBLUE}No changes detected in target networks{bc.ENDC}')

            print()
        
            loop_count+=1
            
            print()
            endTime = time()
            duration = round(endTime-startTime,2)
            if duration > longest_loop: longest_loop = duration
            #print()
            if duration < 60:
                print(f'\t{bcolors.OKBLUE}Loop completed in {bcolors.WARNING}{duration}{bcolors.OKBLUE} seconds')
            else:
                duration = round(duration / 60,2)
                print(f'\t{bcolors.OKBLUE}Loop completed in {bcolors.WARNING}{duration}{bcolors.OKBLUE} minutes')


            total_networks = len(mNets)
            print(f'\t{bcolors.OKBLUE}Total Networks in scope{bcolors.BLINK_FAIL} {total_networks}{bcolors.ENDC}')
            mins = round(longest_loop/60,2)
            print(f'\t{bcolors.OKBLUE}Longest Loop [{bcolors.WARNING} {mins} {bcolors.OKBLUE}] minutes{bcolors.ENDC}')



            print()
            print(f'\t{bcolors.HEADER}****************************{bcolors.FAIL}END LOOP{bcolors.HEADER}*****************************')
            print(bcolors.ENDC)
            print()
            
            sleep(5)
            #while count_sleep > 0:
            #    time.sleep(1)
    #       #     print(f'{bcolors.OKGREEN}z')
            #    count_sleep -= 1
            #print(bcolors.ENDC)
            print()
            #break #only used when wiping all

            if cfg['LOOP'] == False:
                loop = False
            #if loop_count > 5:
            #    loop = False
            # while loop
        return


if __name__ == '__main__':
    safety_loop = 0
    while True:
        safety_loop += 1
        #try:
        startScript = time()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main()) 
        endScript = time()
        duration = round(endScript - startScript,2)
        print(f'Script completed in [{duration}] Seconds')
        #except:
        #    print(sys.exc_info())
        #    if safety_loop > 10: break
