import struct
import time
import os
import subprocess
import json
import sqlite3
import threading
import traceback
from configparser import ConfigParser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler, BaseHTTPRequestHandler
import logging
from citra import Citra

# newly added kcb
import re
import os
from urllib.request import urlopen, Request
from io import BytesIO
import PySimpleGUI as sg
from PIL import Image, UnidentifiedImageError

# pysimplegui settings et al
track_title = 'Ironmon Tracker'
track_size = (600, 600)
sg.set_options(font=('Franklin Gothic Medium', 16), text_color='white', background_color='black', element_background_color='black', text_element_background_color='black', tooltip_font=('Franklin Gothic Medium', 14), tooltip_time=200)

trackadd=r"trackerdata-kcb.json"

def crypt(data, seed, i):
    value = data[i]
    shifted_seed = seed >> 16
    shifted_seed &= 0xFF
    value ^= shifted_seed
    result = struct.pack("B", value)

    value = data[i + 1]
    shifted_seed = seed >> 24
    shifted_seed &= 0xFF
    value ^= shifted_seed
    result += struct.pack("B", value)

    return result

def crypt_array(data, seed, start, end):
    result = bytes()
    temp_seed = seed

    for i in range(start, end, 2):
        temp_seed *= 0x41C64E6D
        temp_seed &= 0xFFFFFFFF
        temp_seed += 0x00006073
        temp_seed &= 0xFFFFFFFF
        result += crypt(data, temp_seed, i)

    return result

def shuffle_array(data, sv, block_size):
    block_position = [[0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3],
                      [1, 1, 2, 3, 2, 3, 0, 0, 0, 0, 0, 0, 2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2],
                      [2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2, 0, 0, 0, 0, 0, 0, 3, 2, 3, 2, 1, 1],
                      [3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 0, 0, 0, 0, 0, 0]]
    result = bytes()
    for block in range(4):
        start = block_size * block_position[block][sv]
        end = start + block_size
        result += data[start:end]
    return result

def decrypt_data(encrypted_data):
    pv = struct.unpack("<I", encrypted_data[:4])[0]
    sv = ((pv >> 0xD) & 0x1F) % 24

    start = 8
    end = (4 * BLOCK_SIZE) + start

    header = encrypted_data[:8]

    # Blocks
    blocks = crypt_array(encrypted_data, pv, start, end)

    # Stats
    stats = crypt_array(encrypted_data, pv, end, len(encrypted_data))

    final_result = header + shuffle_array(blocks, sv, BLOCK_SIZE) + stats

    return final_result

class Pokemon:
    def __init__(self, encrypted_data):
        first_byte = encrypted_data[0]
        if first_byte != 0:
            self.raw_data = decrypt_data(encrypted_data)
        else:
            self.raw_data = ""

    def species_num(self):
        if len(self.raw_data) > 0:
            return struct.unpack("<H", self.raw_data[0x8:0xA])[0]
        else:
            return 0

    def getAtts(self,gamegroupid,gen):
        dex = self.species_num()
        form = struct.unpack("B",self.raw_data[0x1D:0x1E])[0]
        query = f"""select pokemonid from "pokemon.pokemon" where pokemonpokedexnumber = {dex}"""
        print("form",form,"dex",dex)
        match dex:
            #bit 0: fateful encounter flag
            #bit 1: female-adds 2 to resulting form variable, so 2 or 10 instead of 0 or 8
            #bit 2: genderless-adds 4, so 4 or 12
            #bits 3-7: form change flags-8 typical starting point then increases by 8, so 8, 16, 24, etc
            case 641 | 642 | 645:
                if form > 0: ### Therian forms of Tornadus, Thundurus, Landorus
                    query+= " and pokemonsuffix = 'therian'"
            case 6: #Charizard
                match form:
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'mega-x'"
                    case 16 | 18:
                        query+= " and pokemonsuffix = 'mega-y'"
            case 150: ### Mewtwo
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'mega-x'"
                    case 20: ### Mewtwo Y
                        query+= " and pokemonsuffix = 'mega-y'"
            case 201: ### Unown
                query+= " and pokemonsuffix is null"
            case 351: ### Castform
                match form:
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'sunny'"
                    case 16 | 18:
                        query+= " and pokemonsuffix = 'rainy'"
                    case 24 | 26:
                        query+= " and pokemonsuffix = 'snowy'"
            case 382: ### Kyogre
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'primal'"
            case 383: ### Groudon
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'primal'"
            case 386: ### Deoxys
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'attack'"
                    case 20:
                        query+= " and pokemonsuffix = 'defense'"
                    case 28:
                        query+= " and pokemonsuffix = 'speed'"
            case 413: ### Wormadam
                match form:
                    case 10:
                        query+= " and pokemonsuffix = 'sandy'"
                    case 18:
                        query+= " and pokemonsuffix = 'trash'"
                    case 2:
                        query+= " and pokemonsuffix = 'plant'"
            case 421: ### Cherrim
                query+= " and pokemonsuffix is null"
            case 422: ### Shellos
                query+= " and pokemonsuffix is null"
            case 423: ### Gastrodon
                query+= " and pokemonsuffix is null"
            case 479: ### Rotom
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'heat'"
                    case 20:
                        query+= " and pokemonsuffix = 'wash'"
                    case 28:
                        query+= " and pokemonsuffix = 'frost'"
                    case 36:
                        query+= " and pokemonsuffix = 'fan'"
                    case 44:
                        query+= " and pokemonsuffix = 'mow'"
            case 487: ### Giratina
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'origin'"
            case 492: ### Shaymin
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'sky'"
            case 555: ### Darmanitan
                match form:
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'zen'"
            case 585: ### Deerling
                query+= " and pokemonsuffix is null"
            case 586: ### Sawsbuck
                query+= " and pokemonsuffix is null"
            case 646: ### Kyurem
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'white'"
                match form:
                    case 20:
                        query+= " and pokemonsuffix = 'black'"
            case 647: ### Keldeo
                query+= " and pokemonsuffix is null"
            case 648: ### Meloetta
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'pirouette'"
                    case 4: #base form lmao
                        query+= " and pokemonsuffix = 'aria'"
            case 649: ### Genesect
                query+= " and pokemonsuffix is null"
            case 658: ### Greninja
                match form:
                    case 8 | 16:
                        query+= " and pokemonsuffix = 'ash'"
            case 666: ### Vivillon
                query+= " and pokemonsuffix is null"
            case 669: ### Flabébé
                query+= " and pokemonsuffix is null"
            case 670: ### Floette
                match form:
                    case 42: #0 8 16 24 32 40
                        query+= " and pokemonsuffix = 'eternal'"
                    case _:
                        query+= " and pokemonsuffix is null"
            case 671: ### Florges
                query+= " and pokemonsuffix is null"
            case 676: ### Furfrou
                query+= " and pokemonsuffix is null"
            case 678: ### Meowstic
                match form:
                    case 10:
                        query+= " and pokemonsuffix = 'f'"
            case 681: ### Aegislash
                match form:
                    case 0 | 2:
                        query+= " and pokemonsuffix = 'shield'"
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'blade'"
            case 711: ### Gourgeist
                match form:
                    case 16:
                        query+= " and pokemonsuffix = 'average'"
            case 716: ### Xerneas
                query+= " and pokemonsuffix is null"
            case 718: ### Zygarde only needed for gen 7
                match form:
                    case 12:
                        query+= " and pokemonsuffix = '10'"
                    case 20 | 36:
                        query+= " and pokemonsuffix = 'complete'"
            case 720: ### Hoopa
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'unbound'"
            case 741: ### Oricorio
                match form:
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'pom-pom'"
                    case 16 | 18:
                        query+= " and pokemonsuffix = 'pau'"
                    case 24 | 26:
                        query+= " and pokemonsuffix = 'sensu'"
            case 745: ### Lycanroc
                match form:
                    case 16 | 18:
                        query+= " and pokemonsuffix = 'dusk'"
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'midnight'"
            case 746: ### Wishiwashi
                match form:
                    case 8 | 10:
                        query+= " and pokemonsuffix = 'school'"
            case 774: ### Minior 4 12 20 28 36 44 52 60
                match form:
                    case 12 | 20 | 28 | 36 | 44 | 52 | 60: #60 is red
                        query+= " and pokemonsuffix = 'core'"
            case 778: ### Mimikyu
                query+= " and pokemonsuffix is null"
            case 800: ### Necrozma
                match form:
                    case 12:
                        query+= " and pokemonsuffix = 'dusk'"
                    case 20:
                        query+= " and pokemonsuffix = 'dawn'"
                    case 28:
                        query+= " and pokemonsuffix = 'ultra'"
            case 801: ### Magearna
                query+= " and pokemonsuffix is null"
            # case alolan forms-none have separate forms so just case them for if their form > 0
            case 81 | 82 | 100 | 101 | 120 | 121 | 137 | 233 | 292 | 337 | 338 | 343 | 344 | 374 | 375 | 376 | 436 | 437 | 462 | 474 | 489 | 490 | 599 | 600 | 601 | 615 | 622 | 623 | 703 | 774 | 781 | 854 | 855 | 770 | 132 | 144 | 145 | 146 | 201 | 243 | 244 | 245 | 249 | 250 | 251 | 377 | 378 | 379 | 382 | 383 | 384 | 385 | 386 | 480 | 481 | 482 | 483 | 484 | 486 | 491 | 493 | 494 | 638 | 639 | 640 | 643 | 644 | 646 | 647 | 649 | 716 | 717 | 718 | 719 | 721: ### Genderless exceptions
                query+= " and pokemonsuffix is null"
            case _:
                if form == 2:
                    query+= " and pokemonsuffix is null"
                elif form > 0:
                    query+= " and pokemonsuffix ='mega'"
                else:
                    query+= " and pokemonsuffix is null"
        print(query)
        self.id = cursor.execute(query).fetchone()[0]
        self.species,self.suffix,self.name = cursor.execute(f"""select pokemonspeciesname,pokemonsuffix,pokemonname from "pokemon.pokemon" where pokemonid = {self.id}""").fetchone()
        self.suffix = self.suffix or ''
        self.name = self.name.replace(' Form','').replace(' Cloak','')
        self.spritename = self.species.lower()+('' if self.suffix == '' else ('-'+self.suffix))
        self.spriteurl = "https://img.pokemondb.net/sprites/"+getURLAbbr(gamegroupid)+"/normal/"+self.spritename+".png"
        self.bst = cursor.execute(f"""select
                                sum(pokemonstatvalue)
                            from "pokemon.pokemonstat"
                                where pokemonid = {self.id}
                                and generationid = (
                                    select
                                        max(generationid)
                                    from "pokemon.pokemonstat"
                                        where generationid <= {gen}
                                )""").fetchone()[0]    
        self.types = cursor.execute(f"""
                               select
                                    ty.typename
                                from "pokemon.pokemontype" pt
                                    left join "pokemon.type" ty on pt.typeid = ty.typeid
                                where pt.pokemonid = {self.id} and pt.generationid = {gen}                              
                               """).fetchall()
        self.types = [type for type in self.types]
        self.held_item_num=str(struct.unpack("<H", self.raw_data[0xA:0xC])[0])
        self.held_item_name = items[self.held_item_num]['name'].replace("é","&#233;")
        self.ability_num = struct.unpack("B", self.raw_data[0x14:0x15])[0] # Ability
        query = f"""select
                        ab.abilityname
                        ,abilitydescription
                    from "pokemon.generationability" ga
                        left join "pokemon.ability" ab on ga.abilityid = ab.abilityid
                        left join "pokemon.abilitylookup" al on ab.abilityname = al.abilityname
                    where al.abilityindex = {self.ability_num} and ga.generationid <= {gen}
                    order by ga.generationid desc
                    """
        self.abilityname,self.abilitydescription = cursor.execute(query).fetchone()
        self.ability = {'name':self.abilityname,'description':self.abilitydescription}
        self.nature_num = struct.unpack("B", self.raw_data[0x1C:0x1D])[0] ## Nature
        self.nature = cursor.execute(f"""select
                        n.naturename
                    from "pokemon.nature" n
                        left join "pokemon.naturelookup" nl on n.naturename = nl.naturename
                    where nl.natureindex = {self.nature_num}
                    """).fetchone()[0]
        self.friendship = struct.unpack("B", self.raw_data[0xCA:0xCB])[0] ### Friendship
        self.level_met = struct.unpack("<H", self.raw_data[0xDD:0xDF])[0] ####### Level met
        self.level = struct.unpack("B", self.raw_data[0xEC:0xED])[0] ### Current level
        self.cur_hp = struct.unpack("<H", self.raw_data[0xF0:0xF2])[0] ####### Current HP
        self.maxhp = struct.unpack("<H", self.raw_data[0xF2:0xF4])[0] ## Max HP
        self.attack = struct.unpack("<H", self.raw_data[0xF4:0xF6])[0] ## Attack stat
        self.defense = struct.unpack("<H", self.raw_data[0xF6:0xF8])[0] ## Defense stat
        self.speed = struct.unpack("<H", self.raw_data[0xF8:0xFA])[0] ## Speed stat
        self.spatk = struct.unpack("<H", self.raw_data[0xFA:0xFC])[0] ## Special attack stat
        self.spdef = struct.unpack("<H", self.raw_data[0xFC:0xFE])[0] ## Special defense stat
        self.evhp = struct.unpack("B", self.raw_data[0x1E:0x1F])[0]
        self.evattack = struct.unpack("B", self.raw_data[0x1F:0x20])[0]
        self.evdefense = struct.unpack("B", self.raw_data[0x20:0x21])[0]
        self.evspeed = struct.unpack("B", self.raw_data[0x21:0x22])[0]
        self.evspatk = struct.unpack("B", self.raw_data[0x22:0x23])[0]
        self.evspdef = struct.unpack("B", self.raw_data[0x23:0x24])[0]
        self.ivloc = struct.unpack("<I", self.raw_data[0x74:0x78])[0]
        self.ivhp = (self.ivloc >> 0) & 0x1F ############################## HP IV
        self.ivattack = (self.ivloc >> 5) & 0x1F ############################## Attack IV
        self.ivdefense = (self.ivloc >> 10) & 0x1F ############################# Defense IV
        self.ivspeed = (self.ivloc >> 15) & 0x1F ############################# Speed IV
        self.ivspatk = (self.ivloc >> 20) & 0x1F ############################# Special attack IV
        self.ivspdef = (self.ivloc >> 25) & 0x1F ############################# Special defense IV
        def moves(self):
                def movedescription(id):
                    query = f"""select movedescription from "pokemon.generationmove" where generationmoveid = {id}"""
                    return cursor.execute(query).fetchone()[0]
                move1 = ((0x5A,0x5C),(0x62,0x63))
                move2 = ((0x5C,0x5E),(0x63,0x64))
                move3 = ((0x5E,0x60),(0x64,0x65))
                move4 = ((0x60,0x62),(0x65,0x66))
                for ml,pl in (move1,move2,move3,move4):
                    try:
                        move_num = struct.unpack("<H", self.raw_data[ml[0]:ml[1]])[0]
                        query = f"""
                            select
                                mv.movename,
                                gm.generationmoveid,
                                movepp,
                                typename,
                                movepower,
                                moveaccuracy,
                                movecontactflag,
                                movecategoryname
                            from "pokemon.generationmove" gm
                                left join "pokemon.move" mv on gm.moveid = mv.moveid
                                left join "pokemon.movelookup" ml on mv.movename = ml.movename
                                left join "pokemon.type" ty on gm.typeid = ty.typeid
                                left join "pokemon.movecategory" mc on gm.movecategoryid = mc.movecategoryid
                            where ml.moveindex = {move_num} and gm.generationid = {gen}"""
                        movename,id,pp,type,power,acc,contact,category = cursor.execute(query).fetchone()
                        yield {'name':movename,
                            'description':movedescription(id),
                                'pp':struct.unpack("<B",self.raw_data[pl[0]:pl[1]])[0],
                                'maxpp':int(pp),
                                'type':type,
                                'power':power,
                                'acc':acc,
                                'contact':contact,
                                'category':category
                            }
                    except:
                        yield {'name':'',
                               'description':'',
                               'pp':0,
                               'maxpp':0,
                                'type':None,
                                'power':0,
                                'acc':0,
                                'contact':False,
                                'category':None}
                    
        self.moves = [move for move in moves(self)]
        try:
            self.evotype,self.evoitem,self.evolevel,self.evostring,self.evolocation = cursor.execute(f"""
                                            SELECT
                                                evolutiontypename,
                                                itemname,
                                                pokemonevolutionlevel,
                                                pokemonevolutionuniquestring,
                                                locationname
                                            FROM "pokemon.pokemonevolutioninfokaizo" peik
                                                LEFT JOIN "pokemon.item" it ON peik.itemid = it.itemid
                                                LEFT JOIN "pokemon.pokemon" target ON peik.targetpokemonid = target.pokemonid
                                                LEFT JOIN "pokemon.evolutiontype" evot ON peik.evolutiontypeid = evot.evolutiontypeid
                                                LEFT JOIN "pokemon.location" loc ON peik.locationid = loc.locationid
                                                WHERE gamegroupid IN (
                                                    SELECT
                                                        gamegroupid
                                                    FROM "pokemon.gamegroup"
                                                        WHERE gamegrouporder < (
                                                            SELECT
                                                                gamegrouporder
                                                            FROM "pokemon.gamegroup"
                                                                WHERE gamegroupid = '{gamegroupid}'
                                                            )
                                                    )
                                                AND basepokemonid = {str(self.id)}
            """).fetchone()
            self.evo = True
        except:
            self.evo = False
        self.statusbyte = struct.unpack("<B",self.raw_data[0xE8:0xE9])[0] ### Status byte
        match self.statusbyte:
            case 1:
                self.status = 'Paralyzed'
            case 2:
                self.status = 'Asleep'
            case 3:
                self.status = 'Frozen'
            case 4:
                self.status = 'Burned'
            case 5:
                self.status = 'Poisoned'
            case _:
                self.status = ''
        
    def getStatChanges(self):
            raised,lowered = cursor.execute(f"""
            select
                    raisedstat.statname
                    ,loweredstat.statname
                from "pokemon.nature" n
                    left join "pokemon.stat" raisedstat on n.raisedstatid = raisedstat.statid
                    left join "pokemon.stat" loweredstat on n.loweredstatid = loweredstat.statid
                where n.naturename = '{self.nature}'
                """).fetchone()
            for stat in ('Attack','Defense','Special Attack','Special Defense','Speed'):
                if stat == raised:
                    yield 'raised'
                elif stat == lowered:
                    yield 'lowered'
                else:
                    yield ''

    def getMoves(self,gamegroupid):
        learnedcount = 0
        query = f"""
            select
                pokemonmovelevel
            from "pokemon.pokemonmove" pm
                left join "pokemon.pokemonmovemethod" pmm on pm.pokemonmovemethodid = pmm.pokemonmovemethodid
                where gamegroupid = {gamegroupid}
                    and pokemonmovemethodname = 'Level up'
                    and pokemonmovelevel > 1
                    and pokemonid = {self.id}
                order by pokemonmovelevel
        """
        learnlist = cursor.execute(query).fetchall()
        nextmove = None
        totallearn = 0
        learnstr = ''
        for learn in learnlist:
            learnstr+=str(learn[0])+', '
            if int(learn[0]) > 1:
                totallearn+=1
        for learn in learnlist:
            if not int(learn[0]) <= int(self.level):
                nextmove = learn[0]
                break
            elif int(learn[0]) > 1:
                learnedcount+=1
        return totallearn,nextmove,learnedcount,learnstr[0:len(learnstr)-2]

    def getCoverage(self,gen,gamegroupid):
        types = []
        for move in self.moves:
            if move['power']:
                if move['power'] > 0:
                    types.append(move['type'])
        monTypes = f"""
            with montypes as (
                select distinct
                    mon.pokemonid as pokemonid,
                    type1.typeid as type1id,
                    type2.typeid as type2id,
                    pt1.generationid as gen
                from "pokemon.pokemon" mon
                    join "pokemon.pokemontype" pt1 on mon.pokemonid = pt1.pokemonid and pt1.pokemontypeorder = 1 and pt1.generationid = {gen}
                    left join "pokemon.pokemontype" pt2 on mon.pokemonid = pt2.pokemonid and pt2.pokemontypeorder = 2 and pt2.generationid = {gen}
                    join "pokemon.type" type1 on pt1.typeid = type1.typeid
                    left join "pokemon.type" type2 on pt2.typeid = type2.typeid
                    join "pokemon.gamegroup" gg on pt1.generationid = gg.generationid and gg.gamegroupid = {gamegroupid}
                    join "pokemon.game" gm on gg.gamegroupid = gm.gamegroupid
                    join "pokemon.pokemongameavailability" pga on mon.pokemonid = pga.pokemonid and gm.gameid = pga.gameid and pga.gameid
                    ),
        """
        monbsts = f"""
            monbsts as (
                select
                    ps.pokemonid as pokemonid,
                    mt.type1id,
                    mt.type2id,
                    mt.gen,
                    sum(ps.pokemonstatvalue) as bst
                from "pokemon.pokemonstat" ps
                    join montypes mt on ps.generationid = mt.gen AND ps.pokemonid = mt.pokemonid
                    GROUP BY 1,2,3,4
            ),
        """
        attackingdamage = f"""
            attackingdmg as (
                select
                    mb.pokemonid as pokemoeeeeeeenid,
                    mb.type1id as type1id,
                    mb.type2id as type2id,
                    max(tm1.damagemodifier*coalesce(tm2.damagemodifier,1)) as dmgmod
                from monbsts mb
                    join "pokemon.typematchup" tm1 on mb.type1id = tm1.defendingtypeid and tm1.generationid = mb.gen
                    left join "pokemon.typematchup" tm2
                        on mb.type2id = tm2.defendingtypeid
                        and tm1.attackingtypeid = tm2.attackingtypeid
                        and tm2.generationid = mb.gen
                    join "pokemon.type" attackingtype on tm1.attackingtypeid = attackingtype.typeid
                where attackingtype.typename in {str(types).replace('[','(').replace(']',')')}
                group by 1,2,3

            )
        """
        coveragecountsquery = f"""
                select
                    ad.dmgmod,
                    count(ad.pokemonid)
                from attackingdmg ad
                group by 1
                order by 1 asc
        """
        coveragecounts = cursor.execute(monTypes+monbsts+attackingdamage+coveragecountsquery).fetchall()
        # topbstsquery = f"""
        #     select 
        #         mb.bst,
        #         mon.pokemonname
        #     from attackingdmg ad
        #         join monbsts mb on ad.pokemonid = mb.pokemonid
        #         join "pokemon.pokemon" mon on ad.pokemonid = mon.pokemonid
        #     order by ad.dmgmod asc, mb.bst desc limit 10
        # """
        # topbsts = cursor.execute(monTypes+monbsts+attackingdamage+topbstsquery).fetchall()
        return coveragecounts#,topbsts
        

#######################################################################


class Pokemon6(Pokemon):
    def __init__(self, data):
        Pokemon.__init__(self, data)

class Pokemon7(Pokemon):
    def __init__(self, data):
        Pokemon.__init__(self, data)

def getGame(c):
    partylist=[0x8CE1CE8,0x8CF727C,0x34195E10,0x33F7FA44]
    try:
        for item in range(0,4):
            for slot in range(0, 6):
                if read_party(c,partylist[item])[slot].species_num() in range(1,808):
                    namelist=["X/Y","OmegaRuby/AlphaSapphire","Sun/Moon","UltraSun/UltraMoon"]
                    return namelist[item]
    except Exception as e:
        print(e)

def getaddresses(c):
    getGam=getGame(c)
    if getGam=='X/Y':
        partyaddress=0x8CE1CE8
        battlewildpartyadd=142625392
        battlewildoppadd=142622412
        battletrainerpartyadd=142622504
        battletraineroppadd=142625484
        curoppadd=138545352
        wildppadd=136331232
        trainerppadd=136338160
        mongap=580
    elif getGam=='OmegaRuby/AlphaSapphire':
        partyaddress=0x8CF727C
        battlewildpartyadd=0x8CF727C-6000000+812440
        battlewildoppadd=0x8CF727C-6000000+815420
        battletrainerpartyadd=0x8CF727C-6000000+809556
        battletraineroppadd=0x8CF727C-6000000+812536
        curoppadd=0x8CF727C-0xAF2F5C+0x22EA60 #little endian
        wildppadd=0x8CF727C-0xAF2F5C-20 #0x8CF727C-0xAF2F5C
        trainerppadd=0x8CF727C-0xAF2F5C-20+6928
        mongap=580 #Gen 6 has a gap between each mon's data, and goes directly from your mons to the opponent's...
    elif getGam=='Sun/Moon':
        partyaddress=0x34195E10
        battlewildpartyadd=0x34195E10-30000000+5705168
        battlewildoppadd=0x34195E10-30000000+5702188
        battletrainerpartyadd=0x33F7FA44-30000000+7995384
        battletraineroppadd=0x33F7FA44-30000000+7998364
        curoppadd=0x34195E10-68732064+68472752
        wildppadd=0x34195E10-68732064-34
        trainerppadd=0x34195E10-68732064-34
        mongap=816 #while Gen 7 spaces them out, so its 6 slots for your mon, 6 slots for teammates, then 6 slots for enemies.
    elif getGam=='UltraSun/UltraMoon':
        partyaddress=0x33F7FA44
        battlewildpartyadd=0x33F7FA44-30000000+7008668
        battlewildoppadd=0x33F7FA44-30000000+7011648 
        battletrainerpartyadd=0x33F7FA44-30000000+7110648
        battletraineroppadd=0x33F7FA44-30000000+7113628
        curoppadd=0x33F7FA44-0x3f760d4+66286592
        wildppadd=0x33F7FA44-0x3f760d4-34
        trainerppadd=0x33F7FA44-0x3f760d4-34
        mongap=816
    if read_party(c,battlewildoppadd)[0].species_num() in range(1,808) and int.from_bytes(c.read_memory(wildppadd,1))<65:
        return battlewildpartyadd,battlewildoppadd,wildppadd,curoppadd,'w',mongap
    elif read_party(c,battletraineroppadd)[0].species_num() in range(1,808) and int.from_bytes(c.read_memory(trainerppadd,1))<65:
        return battletrainerpartyadd,battletraineroppadd,trainerppadd,curoppadd,'t',mongap
    else:
        return partyaddress,0,0,0,'p',mongap
def cls():
    os.system('cls' if os.name=='nt' else 'clear')

def read_party(c,party_address):
    party = []    
    for i in range(6):
        read_address = party_address + (i * SLOT_OFFSET)
        party_data = c.read_memory(read_address, SLOT_DATA_SIZE)
        stats_data = c.read_memory(read_address + SLOT_DATA_SIZE + STAT_DATA_OFFSET, STAT_DATA_SIZE)
        if party_data and stats_data:
            data = party_data + stats_data
            try:
                pokemon = Pokemon6(data)
                party.append(pokemon)
            except ValueError:
                traceback.print_exc()
                pass
    return party
class server(SimpleHTTPRequestHandler):
    def do_GET(self):
        logging.info("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))
        SimpleHTTPRequestHandler.do_GET(self)
    def do_POST(self):
        content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
        post_data = self.rfile.read(content_length) # <--- Gets the data itself
        logging.info("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n",str(self.path), str(self.headers), post_data.decode('utf-8'))
        datajson=json.loads(post_data)
        with open(trackadd,'w') as f:
            json.dump(datajson,f)
def launchHTTP(server_class=HTTPServer, handler_class=server, port=8000):
    logging.basicConfig(level=logging.INFO)
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    logging.info('Starting httpd...\n')
    print(httpd)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    else:
        print("Please direct an OBS Browser Source to http://localhost:8000/tracker.html or ./tracker.html")
    httpd.server_close()
    logging.info('Stopping httpd...\n')
#def launch2():
    #httpd = HTTPServer(('localhost', 8000), SimpleHTTPRequestHandler)
    #httpd.serve_forever()
def print_bits(value):
    binary = bin(value)[2:].zfill(8)
    bits = [bool(int(bit)) for bit in binary]
    print(bits)

def analyze_statuses(self):
    print('begin statuses')
    # print('statuses:', self.statuses)
    print_bits(self.statusbyte)
    # Analyze bit positions
    print('Asleep:', self.asleep)
    print('Poisoned:', self.poisoned)
    print('Burned:', self.burned)
    print('Frozen:', self.frozen())
    print('Paralyzed:', self.paralyzed)
    # print('Toxic:', self.badlypoisoned())
    print('end statuses')

def calcPower(pkmn,move):
    if move in ('Eruption','Water Spout'):
        return int(int(pkmn.cur_hp)/int(pkmn.maxhp)*150)
    elif move['name']=='Return':
        return round(pkmn.friendship/2.5)
    elif move['name']=="Frustration":
        return round((255-pkmn.friendship)/2.5)
    elif move["name"] in ("Low Kick","Grass Knot"):
        return "WT"
    elif move['name']=="Fling":
        return "ITEM"
    elif move['name'] in ("Crush Grip","Wring Out"):
        return ">HP"
    elif move['name'] in ("Flail","Reversal"):
        if pkmn.hp>=.6875:
            return 20
        elif pkmn.hp>=.3542:
            return 40
        elif pkmn.hp>=.2083:
            return 80
        elif pkmn.hp>=.1042:
            return 100
        elif pkmn.hp>=.0417:
            return 150
        elif pkmn.hp<.0417:
            return 200
        else:
            return "ERR"
    else:
        return ('-' if not move['power'] else int(move['power']))
    
def movetype(pkmn,move,item):
    if move=="Revelation Dance":
        return (pkmn.types)[0]
    elif move=="Hidden Power":
        return "Null"
    elif move=="Natural Gift":
        return "Normal"
    elif move=="Judgement":
        if item=="298":
            return "Fire"
        elif item=="299":
            return "Water"
        elif item=="300":
            return "Electric"
        elif item=="301":
            return "Grass"
        elif item=="302":
            return "Ice"
        elif item=="303":
            return "Fighting"
        elif item=="304":
            return "Poison"
        elif item=="305":
            return "Ground"
        elif item=="306":
            return "Flying"
        elif item=="307":
            return "Psychic"
        elif item=="308":
            return "Bug"
        elif item=="309":
            return "Rock"
        elif item=="310":
            return "Ghost"
        elif item=="311":
            return "Dragon"
        elif item=="312":
            return "Dark"
        elif item=="313":
            return "Steel"
        elif item=="644":
            return "Fairy"
        else:
            return "Normal"
    elif move=="Techno Blast":
        if item=="116":
            return "Water"
        elif item=="117":
            return "Electric"
        elif item=="118":
            return "Fire"
        elif item=="119":
            return "Ice"
        else:
            return "Normal"
    elif move=="Multi-Attack":
        if item=="912":
            return "Fire"
        elif item=="913":
            return "Water"
        elif item=="915":
            return "Electric"
        elif item=="914":
            return "Grass"
        elif item=="917":
            return "Ice"
        elif item=="904":
            return "Fighting"
        elif item=="906":
            return "Poison"
        elif item=="907":
            return "Ground"
        elif item=="905":
            return "Flying"
        elif item=="916":
            return "Psychic"
        elif item=="909":
            return "Bug"
        elif item=="908":
            return "Rock"
        elif item=="910":
            return "Ghost"
        elif item=="918":
            return "Dragon"
        elif item=="919":
            return "Dark"
        elif item=="911":
            return "Steel"
        elif item=="920":
            return "Fairy"
        else:
            return "Normal"
    else:
        return move['type']
    
def getURLAbbr(game):
    if game == 15:
        return 'x-y'
    elif game == 16:
        return 'omega-ruby-alpha-sapphire/dex' ## ORAS sprites end in /dex
    else:
        return 'home'
    
def resize(image_file, new_size, encode_format='PNG'):
    im = Image.open(image_file)
    new_im = im.resize(new_size, Image.NEAREST)
    with BytesIO() as buffer:
        new_im.save(buffer, format=encode_format)
        data = buffer.getvalue()
    return data

def run():
    try:
        #print('connecting to citra')
        c = Citra()
        #print('connected to citra')
        game=getGame(c)
        gamegroupid,gamegroupabbreviation,gen = cursor.execute(f"""
                select
                    gg.gamegroupid
                    ,gg.gamegroupabbreviation
                    ,gg.generationid
                from "pokemon.gamegroup" gg
                where gamegroupname = '{game}'""").fetchone()
        print('running..')
        
        ### SET UP TRACKER GUI ###
        topcol1 = [
            [sg.Text('Loading...', size=(20,1), key='-slot-'),],
            [sg.Image(key='-monimg-')], 
            [sg.Text(justification='c', key='-monname-'), sg.Text(font=('Arial', 11, 'bold'), key='-monnum-')],
            [sg.Image(key='-typeimg1-'), sg.Text(key='-typename1-'), sg.Image(key='-typeimg2-', visible=False), sg.Text(key='-typename2-', visible=False),],
            [sg.Text(key='-level-'), sg.Text(key='-evo-', visible = False), sg.Image(key='-status-', visible = False)],
            [sg.Text(key='-ability-')],
            [sg.Text(key='-item-')],
        ]
        topcol2 = [
            [sg.Text('HP:', key='-hplabel-', visible=False)],
            [sg.Text('Atk:', key='-attlabel-', visible=False)],
            [sg.Text('Def:', key='-deflabel-', visible=False)],
            [sg.Text('SpAtk:', key='-spattlabel-', visible=False)],
            [sg.Text('SpDef:', key='-spdeflabel-', visible=False)],
            [sg.Text('Speed:', key='-speedlabel-', visible=False)],
            [sg.Text('BST:', key='-bstlabel-', visible=False)],
        ]
        topcol3 = [
            [sg.Text(key='-hp-')],
            [sg.Text(key='-att-')],
            [sg.Text(key='-def-')],
            [sg.Text(key='-spatt-')],
            [sg.Text(key='-spdef-')],
            [sg.Text(key='-speed-')],
            [sg.Text(key='-bst-')],
        ]

        botcol1 = [
            [sg.Text(key='-movehdr-')],
            [sg.Image(key='-mv1type-'), sg.Text(key='-mv1text-')],
            [sg.Image(key='-mv2type-'), sg.Text(key='-mv2text-')],
            [sg.Image(key='-mv3type-'), sg.Text(key='-mv3text-')],
            [sg.Image(key='-mv4type-'), sg.Text(key='-mv4text-')],
        ]
        botcol2 = [
            [sg.Text(key='-movepphdr-')],
            [sg.Text(key='-mv1pp-')],
            [sg.Text(key='-mv2pp-')],
            [sg.Text(key='-mv3pp-')],
            [sg.Text(key='-mv4pp-')],
        ]
        botcol3 = [
            [sg.Text(key='-movebphdr-')],
            [sg.Text(key='-mv1bp-')],
            [sg.Text(key='-mv2bp-')],
            [sg.Text(key='-mv3bp-')],
            [sg.Text(key='-mv4bp-')],
        ]
        botcol4 = [
            [sg.Text(key='-moveacchdr-')],
            [sg.Text(key='-mv1acc-')],
            [sg.Text(key='-mv2acc-')],
            [sg.Text(key='-mv3acc-')],
            [sg.Text(key='-mv4acc-')],
        ]
        botcol5 = [
            [sg.Text(key='-movecontacthdr-')],
            [sg.Text(key='-mv1ctc-')],
            [sg.Text(key='-mv2ctc-')],
            [sg.Text(key='-mv3ctc-')],
            [sg.Text(key='-mv4ctc-')],
        ]

        topcol1a = topcol2a = topcol3a = []
        botcol1a = botcol2a = botcol3a = botcol4a = botcol5a = botcol6a = []
        layout = [[
            sg.Column([[
                sg.Column(topcol1, element_justification='bottom', key='-TLCOL1-'), 
                sg.Column(topcol2, key='-TLCOL2-'), 
                sg.Column(topcol3, element_justification='right', key='-TLCOL3-')
            ], 
            [
                sg.Column(botcol1), 
                sg.Column(botcol2, element_justification='right'), 
                sg.Column(botcol3, element_justification='right'), 
                sg.Column(botcol4, element_justification='right'), 
                sg.Column(botcol5, element_justification='right')
            ]]), 
            sg.VerticalSeparator(),
            sg.Column([[
                sg.Column(topcol1a, element_justification='bottom'), 
                sg.Column(topcol2a), 
                sg.Column(topcol3a, element_justification='right')
            ], 
            [
                sg.Column(botcol1a), 
                sg.Column(botcol2a, element_justification='right'), 
                sg.Column(botcol3a, element_justification='right'), 
                sg.Column(botcol4a, element_justification='right'), 
                sg.Column(botcol5a, element_justification='right')
            ], 
            [
                sg.Column(botcol6a), 
            ]])
        ]]
        window = sg.Window(track_title, layout, track_size, background_color='black')
        trackdataedit = 0  # creating flag for edits
        loops = 0
        while (True):
            try:
                if c.is_connected():
                    # trackdata=json.load(open(trackadd,"r+"))
                    event, values = window.Read(timeout=8000)
                    if event == sg.WIN_CLOSED:
                        break
                    if loops == 0:
                        trackdata=json.load(open(trackadd,"r+"))
                    partyadd,enemyadd,ppadd,curoppnum,enctype,mongap=getaddresses(c)
                    # print("loops" + str(loops))
                    loops+=1
                    #print('reading party')
                    party1=read_party(c,partyadd)
                    party2=read_party(c,enemyadd)
                    party=party1+party2
                    pk=1
                    #print('read party... performing loop')
                    #skips trainer mons that arent out yet
                    enemynum=int.from_bytes(c.read_memory(curoppnum,2),"little")
                    pkmni=0
                    for pkmn in party:
                        if pkmn in party1:
                            if pkmn.species_num()==0:
                                party1.remove(pkmn)
                    for pkmn in party2:
                        pkmni+=1
                        if pkmn.species_num()!=enemynum:
                            party.remove(pkmn)
                        else:
                            pkmnindex=(pkmni)
                            break
                    typelist=["Normal","Fighting","Flying","Poison","Ground","Rock","Bug","Ghost","Steel","Fire","Water","Grass","Electric","Psychic","Ice","Dragon","Dark","Fairy"]
                    enemytypes=[]
                    try:
                        if gen==6:
                            pke=pkmnindex+len(party1)
                        elif gen==7:
                            pke=pkmnindex+12
                        typereadere=c.read_memory(ppadd+(mongap*(pke-1))-(2*(gen+6)),2) #(2*(gen+6))
                        for byte in typereadere:
                            if typelist[byte] not in enemytypes:
                                enemytypes.append(typelist[byte])
                    except Exception:
                        print(Exception)
                    for pkmn in party:
                        if pkmn.species_num() in range (1,808): ### Make sure the slot is valid & not an egg
                            pkmn.getAtts(gamegroupid,gen)
                            if int(pkmn.cur_hp) > 5000: ### Make sure the memory dump hasn't happened (or whatever causes the invalid values)
                                continue
                            if pkmn in party2:
                                if gen==6:
                                    pk=pkmnindex+len(party1)
                                elif gen==7:
                                    pk=pkmnindex+12
                            if enctype!='p':
                                #grabs in battle types
                                pkmntypes=[]
                                typereader=c.read_memory(ppadd+(mongap*(pk-1))-(2*(gen+6)),2)
                                for byte in typereader:
                                    if typelist[byte] not in pkmntypes:
                                        pkmntypes.append(typelist[byte])
                                # print('unknown flags')
                                # print_bits(pkmn.alt_form)
                                # print_bits(pkmn.unknown_flags_ea())
                                # print_bits(pkmn.unknown_flags_eb())
                                # analyze_statuses(pkmn)
                                #### Begin Pokemon div
                                if pkmn in party2:
                                    pkd=2
                                else:
                                    pkd=1
                                ##### TYPES, STATS, ABIILITIES, ETC.
                                for type in pkmn.types:
                                    window['-typeimg{}-'.format(pkmn.types.index(type) + 1)].Update(resize('images/types/{}.png'.format(type[0]), (27, 24)), visible = True)
                                    window['-typename{}-'.format(pkmn.types.index(type) + 1)].Update('{}'.format(type[0]), text_color='#999999', visible = True)
                                    if len(pkmn.types) == 1:
                                        window['-typeimg2-'].Update(visible = False)
                                        window['-typename2-'].Update(visible = False)
                                if pkmn.evo:
                                    # evotype = ('' if not pkmn.evotype else pkmn.evotype)
                                    evoitem = ('' if not pkmn.evoitem else 'w/'+pkmn.evoitem)
                                    evofriend = ('' if pkmn.evotype != 'Friendship' else 'w/ high friendship')
                                    evolevel = ('' if not pkmn.evolevel else '@ level '+str(int(pkmn.evolevel)))
                                    evostring = ('' if not pkmn.evostring else pkmn.evostring)
                                    evoloc = ('' if not pkmn.evolocation else 'in '+pkmn.evolocation)
                                    window['-evo-'].update(' > ')
                                    window['-evo-'].set_tooltip('Evolves {}{}{}{}{}'.format(evoitem, evofriend, evolevel, evostring, evoloc), visible = True)
                                else:
                                    window['-evo-'].update(visible = False)
                                if gen==6:
                                    levelnum=int.from_bytes(c.read_memory(ppadd+(mongap*(pk-1))-256,1))
                                    batabilnum=int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))+6-264),1))
                                    hpnum=[int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-264),2),"little"),int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-266),2),"little")]
                                elif gen==7:
                                    levelnum=int.from_bytes(c.read_memory(ppadd+(mongap*(pk-1))-486,1))
                                    batabilnum=int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))+0x36),1))
                                    hpnum=[int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-494),2),"little"),int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-496),2),"little")]
                                if pkmn.status != '':
                                    if int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-264),2),"little")!=0:
                                        x=0
                                    else:
                                        x=0
                                else:
                                    x=0
                                window['-slot-'].Update('Slot {} - {}'.format(str(party.index(pkmn)+1), 'Battle'))
                                window['-monimg-'].Update(resize('images/homemodels/{}.png'.format(pkmn.name), (120,120)))
                                window['-monname-'].Update(pkmn.name.replace("Farfetchd","Farfetch'd"))
                                window['-monnum-'].Update('#{}'.format(str(pkmn.species_num())))
                                window['-level-'].Update('Level: {}'.format(levelnum))
                                window['-level-'].set_tooltip('Seen at {}'.format(trackdata[pkmn.name]["levels"]))
                                if pkmn in party1: 
                                    query=f"""select
                                            ab.abilityname
                                            ,abilitydescription
                                        from "pokemon.generationability" ga
                                            left join "pokemon.ability" ab on ga.abilityid = ab.abilityid
                                            left join "pokemon.abilitylookup" al on ab.abilityname = al.abilityname
                                        where al.abilityindex = {batabilnum} and ga.generationid <= {gen} 
                                        order by ga.generationid desc
                                        """ 
                                    abilityname,abilitydescription = cursor.execute(query).fetchone()
                                    ### STATS ########
                                    #print(int.from_bytes(c.read_memory((ppadd+(mongap*(pk-1))-264),1)))
                                    attackchange,defchange,spatkchange,spdefchange,speedchange = pkmn.getStatChanges()
                                    ### MOVES ########
                                    totallearn,nextmove,learnedcount,learnstr = pkmn.getMoves(gamegroupid)
                                    # counts = pkmn.getCoverage(gen,gamegroupid)
                                    # countstr = ''
                                    # for dmg,count in counts:
                                    #     countstr+='<div class="damage-bracket">['+str(dmg)+'x]</div>'
                                    #     countstr+='<div class="bracket-count">'+str(count)+'</div>'
                                    nmove = (' - ' if not nextmove else nextmove)
                                    window['-ability-'].Update(str(pkmn.ability['name']))
                                    window['-ability-'].set_tooltip(str(pkmn.ability['description']))
                                    window['-item-'].Update(pkmn.held_item_name)
                                    window['-hplabel-'].Update(visible = True)
                                    window['-attlabel-'].Update(visible = True)
                                    window['-deflabel-'].Update(visible = True)
                                    window['-spattlabel-'].Update(visible = True)
                                    window['-spdeflabel-'].Update(visible = True)
                                    window['-speedlabel-'].Update(visible = True)
                                    window['-bstlabel-'].Update(visible = True)
                                    window['-hp-'].Update('{}/{}'.format(hpnum[0], hpnum[1]))
                                    window['-hp-'].set_tooltip('EV: ' + str(pkmn.evhp))
                                    window['-att-'].Update(pkmn.attack)
                                    window['-att-'].set_tooltip('EV: ' + str(pkmn.evattack))
                                    window['-def-'].Update(pkmn.defense)
                                    window['-def-'].set_tooltip('EV: ' + str(pkmn.evdefense))
                                    window['-spatt-'].Update(pkmn.spatk)
                                    window['-spatt-'].set_tooltip('EV: ' + str(pkmn.evspatk))
                                    window['-spdef-'].Update(pkmn.spdef)
                                    window['-spdef-'].set_tooltip('EV: ' + str(pkmn.evspdef))
                                    window['-speed-'].Update(pkmn.speed)
                                    window['-speed-'].set_tooltip('EV: ' + str(pkmn.evspeed))
                                    window['-bst-'].Update(pkmn.bst)
                                    window['-movehdr-'].update('Moves {}/{} ({})'.format(learnedcount, totallearn, nmove))
                                    window['-movehdr-'].set_tooltip(learnstr)
                                    window['-movepphdr-'].update('PP')
                                    window['-movebphdr-'].update('BP')
                                    window['-moveacchdr-'].update('Acc')
                                    window['-movecontacthdr-'].update('C')
                                    for move in pkmn.moves:
                                        stab = ''
                                        movetyp=movetype(pkmn,move,pkmn.held_item_num)
                                        for type in pkmn.types:
                                            if move['type'] == type[0]:
                                                stab = move['type']
                                                continue
                                        typetable={
                                            "Normal":[1,1,1,1,1,.5,1,0,.5,1,1,1,1,1,1,1,1,1,1],
                                            "Fighting":[2,1,.5,.5,1,2,.5,0,2,1,1,1,1,.5,2,1,2,.5,1],
                                            "Flying":[1,2,1,1,1,.5,2,1,.5,1,1,2,.5,1,1,1,1,1,1],
                                            "Poison":[1,1,1,.5,.5,.5,1,.5,0,1,1,2,1,1,1,1,1,2,1],
                                            "Ground":[1,1,0,2,1,2,.5,1,2,2,1,.5,2,1,1,1,1,1,1],
                                            "Rock":[1,.5,2,1,.5,1,2,1,.5,2,1,1,1,1,2,1,1,1,1],
                                            "Bug":[1,.5,.5,.5,1,1,1,.5,.5,.5,1,2,1,2,1,1,2,.5,1],
                                            "Ghost":[0,1,1,1,1,1,1,2,1,1,1,1,1,2,1,1,.5,1,1],
                                            "Steel":[1,1,1,1,1,2,1,1,.5,.5,.5,1,.5,1,2,1,1,2,1],
                                            "Fire":[1,1,1,1,1,.5,2,1,2,.5,.5,2,1,1,2,.5,1,1,1],
                                            "Water":[1,1,1,1,2,2,1,1,1,2,.5,.5,1,1,1,.5,1,1,1],
                                            "Grass":[1,1,.5,.5,2,2,.5,1,.5,.5,2,.5,1,1,1,.5,1,1,1],
                                            "Electric":[1,1,2,1,0,1,1,1,1,1,2,.5,.5,1,1,.5,1,1,1],
                                            "Psychic":[1,2,1,2,1,1,1,1,.5,1,1,1,1,.5,1,1,0,1,1],
                                            "Ice":[1,1,2,1,2,1,1,1,.5,.5,.5,2,1,1,.5,2,1,1,1],
                                            "Dragon":[1,1,1,1,1,1,1,1,.5,1,1,1,1,1,1,2,1,0,1],
                                            "Dark":[1,.5,1,1,1,1,1,2,1,1,1,1,1,2,1,1,.5,.5,1],
                                            "Fairy":[1,2,1,.5,1,1,1,1,.5,.5,1,1,1,1,1,2,2,1,1],
                                            "Null":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
                                            "-":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                                        }
                                        #defines the columns for the arrays corresponding to the type hit
                                        typedic={"Normal":0,"Fighting":1,"Flying":2,"Poison":3,"Ground":4,"Rock":5,"Bug":6,"Ghost":7,"Steel":8,"Fire":9,"Water":10,"Grass":11,"Electric":12,"Psychic":13,"Ice":14,"Dragon":15,"Dark":16,"Fairy":17,"Null":18}
                                        typemult=1
                                        antici=0
                                        if movetyp!=None:
                                            for type in enemytypes:
                                                typemult=typemult*(typetable[movetyp][typedic[type]])
                                        if move["category"]!="Non-Damaging":
                                            if typemult==.25:
                                                image="4"
                                            elif typemult==.5:
                                                image="5"
                                            elif typemult==1:
                                                image="6"
                                            elif typemult==2:
                                                image="7"
                                                antici = 1
                                            elif typemult==4:
                                                image="8"
                                                antici = 1
                                            elif typemult==0:
                                                image="X"
                                        else:
                                            image="6"
                                        movepower = calcPower(pkmn,move)
                                        acc = '-' if not move['acc'] else int(move['acc'])
                                        contact = ('Y' if move['contact'] else 'N')
                                        window['-mv{}type-'.format(pkmn.moves.index(move) + 1)].update(resize('images/categories/{}.png'.format(move["category"]), (27,20)))
                                        window['-mv{}text-'.format(pkmn.moves.index(move) + 1)].update(move["name"])
                                        window['-mv{}text-'.format(pkmn.moves.index(move) + 1)].set_tooltip(move["description"])
                                        window['-mv{}pp-'.format(pkmn.moves.index(move) + 1)].update('{}/{}'.format(move["pp"], move["maxpp"]))
                                        window['-mv{}bp-'.format(pkmn.moves.index(move) + 1)].update(movepower)
                                        window['-mv{}acc-'.format(pkmn.moves.index(move) + 1)].update(acc)
                                        window['-mv{}ctc-'.format(pkmn.moves.index(move) + 1)].update(contact)
                                elif (pkmn in party2) & (party.index(pkmn)+1):
                                    query=f"""select
                                            ab.abilityname
                                            ,abilitydescription
                                        from "pokemon.generationability" ga
                                            left join "pokemon.ability" ab on ga.abilityid = ab.abilityid
                                            left join "pokemon.abilitylookup" al on ab.abilityname = al.abilityname
                                        where al.abilityindex = {batabilnum} and ga.generationid <= {gen}
                                        order by ga.generationid desc
                                        """
                                    abilityname,abilitydescription = cursor.execute(query).fetchone()
                                    startupabils=["Air Lock","Cloud Nine","Delta Stream","Desolate Land","Download","Drizzle","Drought","Forewarn","Frisk","Imposter","Intimidate","Mold Breaker","Pressure","Primordial Sea","Sand Stream","Slow Start","Snow Warning","Teravolt","Turboblaze","Trace","Unnerve","Aura Break","Fairy Aura","Dark Aura",]
                                    if antici == 1:
                                        startupabils.append('Anticipation')
                                    if abilityname in startupabils:
                                        if pkmn.abilityname not in trackdata[pkmn.species]['abilities']:
                                            trackdata[pkmn.species]['abilities'].append(pkmn.abilityname)
                                            trackdataedit = 1
                                    else:
                                        x=0
                                    # pkmn_note = str(trackdata[pkmn.species]['notes'])
                                    # print(pkmn_note)
                                    ### STATS ########
                                    ### MOVES ########
                                    totallearn,nextmove,learnedcount,learnstr = pkmn.getMoves(gamegroupid)
                                    # counts = pkmn.getCoverage(gen,gamegroupid)
                                    # countstr = ''
                                    # for dmg,count in counts:
                                    #     countstr+='<div class="damage-bracket">['+str(dmg)+'x]</div>'
                                    #     countstr+='<div class="bracket-count">'+str(count)+'</div>'
                                    if pkmn.level not in trackdata[pkmn.species]['levels']:
                                        trackdata[pkmn.species]['levels'].append(pkmn.level)
                                        trackdataedit = 1
                                    nmove = (' - ' if not nextmove else nextmove)
                                    for move in pkmn.moves:
                                        if int.from_bytes(c.read_memory(ppadd+(mongap*(pk-1))+(14*(pkmn.moves).index(move)),1))==int.from_bytes(c.read_memory(ppadd+1+(mongap*(pk-1))+(14*(pkmn.moves).index(move)),1)): 
                                            continue
                                        stab = ''
                                        for type in pkmn.types:
                                            if move['type'] == type[0]:
                                                stab = move['type']
                                                continue
                                        movepower = calcPower(pkmn,move)
                                        acc = '-' if not move['acc'] else int(move['acc'])
                                        contact = ('Y' if move['contact'] else 'N')
                                        if move['name'] not in trackdata[pkmn.species]['moves']:
                                            trackdata[pkmn.species]['moves'][move['name']]=[]
                                            trackdataedit = 1
                                        if pkmn.level not in trackdata[pkmn.species]['moves'][move['name']]:
                                            trackdata[pkmn.species]['moves'][move['name']].append(pkmn.level)
                                            trackdataedit = 1
                                pkmntypes=[]
                            elif enctype=='p':
                                ##### TYPES, STATS, ABIILITIES, ETC.
                                for type in pkmn.types:
                                    window['-typeimg{}-'.format(pkmn.types.index(type) + 1)].Update(resize('images/types/{}.png'.format(type[0]), (27, 24)), visible = True)
                                    window['-typename{}-'.format(pkmn.types.index(type) + 1)].Update('{}'.format(type[0]), text_color='#999999', visible = True)
                                    if len(pkmn.types) == 1:
                                        window['-typeimg2-'].Update(visible = False)
                                        window['-typename2-'].Update(visible = False)
                                if pkmn.evo:
                                    evoitem = ('' if not pkmn.evoitem else 'w/'+pkmn.evoitem)
                                    evofriend = ('' if pkmn.evotype != 'Friendship' else 'w/ high friendship')
                                    evolevel = ('' if not pkmn.evolevel else '@ level '+str(int(pkmn.evolevel)))
                                    evostring = ('' if not pkmn.evostring else pkmn.evostring)
                                    evoloc = ('' if not pkmn.evolocation else 'in '+pkmn.evolocation)
                                if pkmn.status != '':
                                    window['-status-'].Update(resize('images/statuses/{}.png', (40, 25)).format(pkmn.status), visible = True)
                                else:
                                    window['-status-'].Update(visible = False)
                                ### MOVES ########
                                totallearn,nextmove,learnedcount,learnstr = pkmn.getMoves(gamegroupid)
                                # counts = pkmn.getCoverage(gen,gamegroupid)
                                # countstr = ''
                                # for dmg,count in counts:
                                #     countstr+='<div class="damage-bracket">['+str(dmg)+'x]</div>'
                                #     countstr+='<div class="bracket-count">'+str(count)+'</div>'
                                nmove = (' - ' if not nextmove else nextmove)
                                for move in pkmn.moves:
                                    stab = ''
                                    movetyp=movetype(pkmn,move,pkmn.held_item_num)
                                    for type in pkmn.types:
                                        if move['type'] == type[0]:
                                            stab = move['type']
                                            continue
                                    movepower = calcPower(pkmn,move)
                                    acc = '-' if not move['acc'] else int(move['acc'])
                                    contact = ('Y' if move['contact'] else 'N')
                                ### UPDATING TRACKER INFO ###
                                window['-slot-'].Update('Slot {} - {}'.format(str(party.index(pkmn)+1), 'Overworld'))
                                window['-monimg-'].Update(resize('images/homemodels/{}.png'.format(pkmn.name), (120,120)))
                                window['-monname-'].Update(pkmn.name.replace("Farfetchd","Farfetch'd"))
                                window['-monnum-'].Update('#{}'.format(str(pkmn.species_num())))
                                window['-level-'].Update('Level: {}'.format(str(pkmn.level)))
                                window['-level-'].set_tooltip('Seen at {}'.format(trackdata[pkmn.name]["levels"]))
                                if pkmn.evo:
                                    window['-evo-'].update(' > ')
                                    window['-evo-'].set_tooltip('Evolves {}{}{}{}{}'.format(evoitem, evofriend, evolevel, evostring, evoloc), visible = True)
                                else:
                                    window['-evo-'].update(visible = False)
                                window['-ability-'].Update(str(pkmn.ability['name']))
                                window['-ability-'].set_tooltip(str(pkmn.ability['description']))
                                window['-item-'].Update(pkmn.held_item_name)
                                window['-hplabel-'].Update(visible = True)
                                window['-attlabel-'].Update(visible = True)
                                window['-deflabel-'].Update(visible = True)
                                window['-spattlabel-'].Update(visible = True)
                                window['-spdeflabel-'].Update(visible = True)
                                window['-speedlabel-'].Update(visible = True)
                                window['-bstlabel-'].Update(visible = True)
                                window['-hp-'].Update('{}/{}'.format(pkmn.cur_hp, pkmn.maxhp))
                                window['-hp-'].set_tooltip('EV: ' + str(pkmn.evhp))
                                window['-att-'].Update(pkmn.attack)
                                window['-att-'].set_tooltip('EV: ' + str(pkmn.evattack))
                                window['-def-'].Update(pkmn.defense)
                                window['-def-'].set_tooltip('EV: ' + str(pkmn.evdefense))
                                window['-spatt-'].Update(pkmn.spatk)
                                window['-spatt-'].set_tooltip('EV: ' + str(pkmn.evspatk))
                                window['-spdef-'].Update(pkmn.spdef)
                                window['-spdef-'].set_tooltip('EV: ' + str(pkmn.evspdef))
                                window['-speed-'].Update(pkmn.speed)
                                window['-speed-'].set_tooltip('EV: ' + str(pkmn.evspeed))
                                window['-bst-'].Update(pkmn.bst)
                                window['-movehdr-'].update('Moves {}/{} ({})'.format(learnedcount, totallearn, nmove))
                                window['-movehdr-'].set_tooltip(learnstr)
                                window['-movepphdr-'].update('PP')
                                window['-movebphdr-'].update('BP')
                                window['-moveacchdr-'].update('Acc')
                                window['-movecontacthdr-'].update('C')
                                for move in pkmn.moves:
                                    stab = ''
                                    movetyp=movetype(pkmn,move,pkmn.held_item_num)
                                    for type in pkmn.types:
                                        if move['type'] == type[0]:
                                            stab = move['type']
                                            continue
                                    movepower = calcPower(pkmn,move)
                                    acc = '-' if not move['acc'] else int(move['acc'])
                                    contact = ('Y' if move['contact'] else 'N')
                                    window['-mv{}type-'.format(pkmn.moves.index(move) + 1)].update(resize('images/categories/{}.png'.format(move["category"]), (27,20)))
                                    window['-mv{}text-'.format(pkmn.moves.index(move) + 1)].update(move["name"])
                                    window['-mv{}text-'.format(pkmn.moves.index(move) + 1)].set_tooltip(move["description"])
                                    window['-mv{}pp-'.format(pkmn.moves.index(move) + 1)].update('{}/{}'.format(move["pp"], move["maxpp"]))
                                    window['-mv{}bp-'.format(pkmn.moves.index(move) + 1)].update(movepower)
                                    window['-mv{}acc-'.format(pkmn.moves.index(move) + 1)].update(acc)
                                    window['-mv{}ctc-'.format(pkmn.moves.index(move) + 1)].update(contact)
                                    continue
                            pk=pk+1
                    with open(trackadd,'w') as f:
                        json.dump(trackdata,f)
                    # if trackdataedit == 1:
                    #     with open(trackadd,'w') as f:
                    #         json.dump(trackdata,f)
                    #     trackdataedit = 0
                    # layout = [[sg.Column(topcol1, element_justification='bottom', key='TL-COL')]]
                    # window = sg.Window(track_title, layout, track_size, background_color='black')
                    # event, values = window.read(timeout=5000)
                    # topcol1 = [
                    #     [sg.Text('Slot {}'.format(str(party.index(pkmn)+1)), size=(20,1), key='SLOT'),],
                    #     [sg.Image(resize('images/homemodels/{}.png'.format(pkmn.name), (120,120)))], 
                    #     [sg.Text(pkmn.name.replace("Farfetchd","Farfetch'd"), justification='c'), sg.Text('#{}'.format(str(pkmn.species_num())), font=('Arial', 11, 'bold'))],
                    #     typegui,
                    #     [sg.Text('Level: '), sg.Text(str(pkmn.level), tooltip='Seen at {}'.format(trackdata[pkmn.name]["levels"])), evogui, statusgui],
                    #     [sg.Text(str(pkmn.ability['name']), tooltip=str(pkmn.ability['description']))],
                    #     [sg.Text(pkmn.held_item_name)],
                    # ]

                    # if event == sg.WIN_CLOSED:
                    #     break
                    # elif event == sg.TIMEOUT_KEY:
                    #     layout = [[sg.Column(topcol1, element_justification='bottom')]]
                    #     window['-slot-'].Update('Slot {}'.format(str(party.index(pkmn)+1)))
                    #     window['-monimg-'].Update(resize('images/homemodels/{}.png'.format(pkmn.name), (120,120)))
                    #     window['-monname-'].Update(pkmn.name.replace("Farfetchd","Farfetch'd"))
                    #     window['-monnum-'].Update('#{}'.format(str(pkmn.species_num())))
                    #     window['-typeimg-'].Update(resize('images/types/{}.png'.format(type[0]), (18, 16)))
                    #     window['-typename-'].Update('{}'.format(type[0]), text_color='#999999')
                    #     window['-level-'].Update('Level: {}'.format(str(pkmn.level)), tooltip='Seen at {}'.format(trackdata[pkmn.name]["levels"]))
                    #     window['-ability-'].Update(str(pkmn.ability['name']), tooltip=str(pkmn.ability['description']))
                    #     window['-item-'].Update(pkmn.held_item_name)

                    # time.sleep(8.5)
            except Exception as e:
                print(e)
                with open('errorlog.txt','a+') as f:
                    errorLog = str(datetime.now())+": "+str(e)+'\n'
                    f.write(errorLog)
                # traceback.print_exc()
                import sys, os, traceback
                exc_type, exc_obj, exc_tb = sys.exc_info()
                tb = traceback.extract_tb(exc_tb)[-1]
                print(exc_type, tb[2], tb[1])
                time.sleep(5)
                print(errorLog)
                if "WinError 10054" in str(e):
                    print("To continue using the tracker, please open a ROM.")
                    print("Waiting for a ROM...")
                    time.sleep(15)
    except Exception as e:
        print(e)
        with open('errorlog.txt','a+') as f:
            errorLog = str(datetime.now())+": "+str(e)+'\n'
            f.write(errorLog)
        import sys, os, traceback
        exc_type, exc_obj, exc_tb = sys.exc_info()
        tb = traceback.extract_tb(exc_tb)[-1]
        print(exc_type, tb[2], tb[1])
        if "cannot unpack non-iterable NoneType object" in str(e):
            print("Waiting for a starter...")
            time.sleep(15)
    finally:
        print("")
        window.close()

BLOCK_SIZE = 56
SLOT_OFFSET = 484
SLOT_DATA_SIZE = (8 + (4 * BLOCK_SIZE))
STAT_DATA_OFFSET = 112
STAT_DATA_SIZE = 22

conn = sqlite3.connect("data/gen67.sqlite")
cursor = conn.cursor()

with open('data/item-data.json','r') as f:
    items = json.loads(f.read())

if __name__ == "__main__" :
    run()