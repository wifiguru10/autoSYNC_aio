#!/usr/bin/ipython3 -i

### changeLog by Nico Darrow

from datetime import *
import copy
from bcolors import bcolors
import meraki.aio
import asyncio

class changelogHelper:
    db = None
    orgs = ""
    watch_list = [] #networkID watch list
    tag_target = ""
    changed_nets = ""
    last_Checkin = ""
    ignoreAPI = ""

    def __init__(self, db, orgs):
        self.db = db
        uniqueOrgs = list(dict.fromkeys(orgs))
        self.orgs = uniqueOrgs
        self.watch_list = []
        self.changed_nets = []
        self.ignoreAPI = True
        self.last_Checkin = datetime.isoformat(datetime.utcnow()) + 'Z'
        return

    #adds network to watch-list
    def addNetwork(self, netid):
        self.watch_list.append(netid)
        uniqueNets = list(dict.fromkeys(self.watch_list)) #dedups
        self.watch_list = uniqueNets
        return

     #adds network to watch-list
    def delNetwork(self, netid):
        if netid in self.watch_list:
            self.watch_list.remove(netid)
        return

    #clears watching networks
    def clearNetworks(self):
        self.watch_list = []
        return

    async def hasChange(self):
        current_time = datetime.isoformat(datetime.utcnow()) + 'Z'
        self.changed_nets = []
        if self.last_Checkin == "":
            self.last_Checkin = current_time
            return False
        
        changes = await self.getChanges(self.last_Checkin)
        hasChange = False
        for c in changes:
            #print(c)
            if 'networkId' in c and c['networkId'] in self.watch_list:
                if 'page' in c and c['page'] == 'via API' and self.ignoreAPI:
                    continue
                else:
                    print(f'{bcolors.FAIL}ChangLog Detected change!{bcolors.ENDC}')
                    #print(c)
                    if not c['networkId'] in self.changed_nets: #remove duplicates
                        self.changed_nets.append(c['networkId'])
                    self.last_Checkin = current_time
                    hasChange = True

            #the following is supposed to sync any new network that has a "TAG" added but isn't currently in the watch_list
            if 'networkId' in c and not c['networkId'] in self.watch_list and len(self.tag_target) > 0 and c['label'] == 'Network tags' and self.tag_target in c['newValue']:
                print(f'{bcolors.WARNING}NEW NETWORK DETECTED{bcolors.ENDC}')
                self.changed_nets.append(c['networkId'])
                self.watch_list.append(c['networkId'])
                hasChange = True

        self.last_Checkin = current_time
#        if hasChange: print(f'{bcolors.OKGREEN}Active Admin Emails:[{bcolors.WARNING}{self.adminEmail}{bcolors.OKGREEN}]{bcolors.ENDC}')
        return hasChange

    async def loadCfgOrg(self, o, TS):
        res = await self.db.organizations.getOrganizationConfigurationChanges(o,startingAfter=TS)
        return res
        
    async def getChanges(self, TS):
        #{ 'ts': '2020-09-17T16:31:54.857306Z',
        #  'adminName': 'Nico Darrow',
        #  'adminEmail': 'ndarrow@cisco.com',
        #  'adminId': '5701',
        #  'networkName': 'AutoSync Test 21',
        #  'networkId': 'N_23423424234234',
        #  'page': 'Organization overview',
        #  'label': 'Network tags',
        #  'oldValue': '["autoSYNC"]',
        #  'newValue': '[]'},
        results = []
        print(f'{bcolors.OKBLUE}Looking for changes at time {bcolors.WARNING}{TS}{bcolors.ENDC}')

        loadOrgsCfgTasks = [self.loadCfgOrg(o, TS) for o in self.orgs]
        for task in asyncio.as_completed(loadOrgsCfgTasks):
            res = await task
            results = results + res

        return results



