import config
import time
from copy import copy
from formats import new_pdb_line
import log

class Tautomer:
    """Tautomers share the same site and atoms
    Tautomers have different charge sets for the same atoms
    """
    def __init__(self, name, site, molecule):
        """
        Args:
            name (str): name of the Tautomer
            site (Site): belonging site
            molecule (TitratingMolecule): belonging molecule

        # Inheritance
        self._molecule
        self._site

        # Tautomer Details
        self._name
        self._charge_set (dict): charge set of the tautomer
                                 key is atom name str
                                 value is charge float
        self._natoms (int): number of atoms of the Tautomer
        Redundant to self._site._natoms as it must be the same 
        between all Tautomers belonging to the same Site.

        # Tautomer Energy Details
        self._esolvation (float): solvation energy
        self._e_back (float): background interaction energy
        self._dg (float): pKint energy
        """
        self._molecule = molecule
        self._site = site
        self._name = name
        self._esolvation = ''
        self._charge_set = {}
        self._natoms = 0
        self._e_back = 0.0
        self._dg = 0.0

    # Set Methods
    def loadChargeSet(self, res_name, ref_tautomer):
        """Reads .st file related to Tautomer with residue name res_name
        Stores charge set related to both the Tautomer and the
        Reference Tautomer

        .st file named TYRtau1.st has charge set of TY0 and reference TY2
                       TYRtau2.st has charge set of TY1 and reference TY2
        """
        tau_number = int(self._name[-1]) + 1
        fname = '{0}/{1}/sts/{2}tau{3}.st'.format(config.script_dir,
                                                  config.params['ffID'],
                                                  res_name, tau_number)
        with open(fname) as f:
            nline = 0
            charge_set1 = {}
            charge_set2 = {}
            floats_1 = []
            floats_2 = []
            for line in f:
                nline += 1
                cols = line.split()
                if nline > 1:
                    atom_name = cols[1]
                    if atom_name == 'C' and res_name == 'CTR':
                        atom_name = 'CT'
                    elif atom_name in ('O1', 'O2') and res_name == 'CTR':
                        atom_name = atom_name[0] + 'T' + atom_name[1]
                    charge_set1[atom_name] = float(cols[-2])
                    charge_set2[atom_name] = float(cols[-1])
                else:
                    self._pKmod = float(line)

        if sum(charge_set1.values()) < 0.001 and sum(charge_set2.values()) > -1.001:
            if config.debug:
                print fname, 'anionic'
            self._charge_set = charge_set1
            ref_tautomer._charge_set = charge_set2
            self._site.setType('a')            
        elif sum(charge_set1.values()) > 0.99 and sum(charge_set2.values()) < 0.001:
            if config.debug:
                print fname, 'cationic'
            self._charge_set = charge_set2
            ref_tautomer._charge_set = charge_set1
            self._site.setType('c')
        self._natoms = len(self._charge_set)
        ref_tautomer._natoms = len(self._charge_set)
        if config.debug:
            print self._charge_set
            print ref_tautomer._charge_set
            print 'finished reading', fname

    def saveDelPhiResults(self, esolvationS, sitpotS, esolvationM, sitpotM):
        self._esolvationS  =  esolvationS
        self._sitpotS      =  sitpotS
        self._esolvationM  =  esolvationM
        self._sitpotM      =  sitpotM

    def setDetailsFromWholeMolecule(self):
        """Set DelPhi parameters to run a calculation of a whole molecule 
        (all sites neutral, except one)"""
        def fix_position(x, y, box_side):
            if x < 0:
                x -= box_side
            if y < 0:
                y -= box_side
            return x, y

        molecule = self._molecule
        delphimol = molecule.getDelPhi()

        # Could have used empty structures
        # TODO: quantify time impact of this quick fix
        p_atpos  = copy(molecule.p_atpos) 
        p_rad3   = copy(molecule.p_rad3)  
        p_chrgv4 = copy(molecule.p_chrgv4)
        atinf    = copy(molecule.atinf)
        p_iatmed = copy(molecule.p_iatmed)

        if config.params['pbc_dim'] == 2:
            box = molecule.box
            half_box_xy = self._site.getCenter()[0]
            site_center = self._site.getCenterOriginal()

            offset_x = half_box_xy - site_center[0]
            offset_y = half_box_xy - site_center[1]
            offset_z = box[2] * 10 # irrelevant, only for debug

        pdb_text = ''
        crg = '!crg file created by gen_files.awk\n'\
              'atom__resnumbc_charge_\n'
        new_atoms = []
        for atom_name, atom_id, atom_position in molecule.iterAtoms():
            aID = atom_position + 1
            aname = atinf[atom_position].value.split()[0]
            resname = atinf[atom_position].value.split()[1]
            resnumb = int(atinf[atom_position].value.split()[2])
            x = float(p_atpos[atom_position][0])
            y = float(p_atpos[atom_position][1])
            z = float(p_atpos[atom_position][2])
            pdb_text += new_pdb_line(aID, aname, resname, resnumb, x, y, z)

            #TODO: quick fix, should be being done only once per site
            if config.params['pbc_dim'] == 2:
                p_atpos[atom_position][0] += offset_x
                p_atpos[atom_position][1] += offset_y
                p_atpos[atom_position][2] += offset_z
                if p_atpos[atom_position][0] < 0:
                    p_atpos[atom_position][0] += box[0] * 10
                if p_atpos[atom_position][1] < 0:
                    p_atpos[atom_position][1] += box[1] * 10

                p_atpos[atom_position][0] = round(p_atpos[atom_position][0], 2)
                p_atpos[atom_position][1] = round(p_atpos[atom_position][1], 2)
                p_atpos[atom_position][2] = round(p_atpos[atom_position][2], 2)

                pbc_atoms = self.add_pbc(p_atpos[atom_position][0],
                                         p_atpos[atom_position][1],
                                         p_atpos[atom_position][2], box[0],
                                         p_rad3[atom_position],
                                         p_chrgv4[atom_position],
                                         atinf[atom_position].value)
                new_atoms += pbc_atoms

            if atom_id in self._site.getAtomNumbersList():
                p_chrgv4[atom_position] = self.getCharge(atom_name)
            else:
                p_chrgv4[atom_position] = 0.0

            if float(p_chrgv4[atom_position]) < 0.0:
                signal = '-'
            else:
                signal = ' '

            crg += '{0:<6}{1:<7}  {3}{2:0<5} \n'.format(aname, resname,
                                                        round(abs(p_chrgv4[atom_position]), 3),
                                                        signal)

        natoms = delphimol.changeStructureSize(molecule._natoms, p_atpos, p_rad3,
                                               p_chrgv4, atinf, p_iatmed, extra_atoms=new_atoms)

        if config.params['pbc_dim'] == 2:
            x = molecule.box[0] * 10 / 2
            y = x
            z = self._site._center[2]
            acent = [x, y, z]
        else:
            acent = self._site._center
        acent = [round(acent[0], 4), round(acent[1], 4), round(acent[2], 3)]

        pdb_text = ''
        for i in range(natoms):
            aID = i + 1
            aname   = molecule._delphimol.atinf[i].value.split()[0]
            resname = molecule._delphimol.atinf[i].value.split()[1]
            resnumb = int(molecule._delphimol.atinf[i].value.split()[2])
            if '-' in aname[0]:
                aname = aname[1:]
                resname = 'PBC'
                resnumb = -666
            x = float(molecule._delphimol.p_atpos[i][0])
            y = float(molecule._delphimol.p_atpos[i][1])
            z = float(molecule._delphimol.p_atpos[i][2])
            #if aID == 383:
            #    exit()
            pdb_text += new_pdb_line(aID, aname, resname, resnumb, x, y, z)

        with open('P_{1}-{0}.pdb'.format(self._name, self._site._res_number), 'w') as f_new:
            x, y, z = acent
            pdb_text += new_pdb_line(-1, 'P', 'CNT', -1, x, y, z)

            pdb_text += new_pdb_line(-2, 'P', 'PDB', -2, 0, 0 , z)
            pdb_text += new_pdb_line(-2, 'P', 'PDB', -2, box[0] * 10, 0, z)
            pdb_text += new_pdb_line(-2, 'P', 'PDB', -2, 0, box[1] * 10, z)
            pdb_text += new_pdb_line(-2, 'P', 'PDB', -2, box[0] * 10, box[1] * 10, z)

            cutoff = box[0] * 10 * 0.1
            pdb_text += new_pdb_line(-3, 'P', 'PDB', -3, cutoff, cutoff , z)
            pdb_text += new_pdb_line(-3, 'P', 'PDB', -3, box[0] * 10 - cutoff, cutoff, z)
            pdb_text += new_pdb_line(-3, 'P', 'PDB', -3, cutoff, box[1] * 10 - cutoff, z)
            pdb_text += new_pdb_line(-3, 'P', 'PDB', -3, box[0] * 10 - cutoff, box[1] * 10 - cutoff, z)
            pdb_text += new_pdb_line(-4, 'P', 'PDB', -4, -cutoff, -cutoff , z)
            pdb_text += new_pdb_line(-4, 'P', 'PDB', -4, box[0] * 10 + cutoff, - cutoff, z)
            pdb_text += new_pdb_line(-4, 'P', 'PDB', -4, -cutoff, box[1] * 10 + cutoff, z)
            pdb_text += new_pdb_line(-4, 'P', 'PDB', -4, box[0] * 10 + cutoff, box[1] * 10 + cutoff, z)

            f_new.write(pdb_text)
        with open('P_{1}-{0}.crg'.format(self._name, self._site._res_number), 'w') as f_new:
            f_new.write(crg)

        return acent

    def setDetailsFromTautomer(self):
        """Set DelPhi parameters to run a calculation 
        of a single site tautomer"""
        molecule = self._molecule
        delphimol = molecule.getDelPhi()

        # Could have used empty structures
        # TODO: quantify time impact of this quick fix
        p_atpos  = copy(molecule.p_atpos)
        p_rad3   = copy(molecule.p_rad3)
        p_chrgv4 = copy(molecule.p_chrgv4)
        atinf    = copy(molecule.atinf)
        p_iatmed = copy(molecule.p_iatmed)

        if config.params['pbc_dim'] == 2:
            box = molecule.box
            half_box_xy = self._site.getCenter()[0]
            site_center = self._site.getCenterOriginal()

            offset_x = half_box_xy - site_center[0]
            offset_y = half_box_xy - site_center[1]
            offset_z = box[2] * 10

        pdb_text = ''
        site_atom_position = -1
        for atom_name, atom_id, atom_position in molecule.iterAtoms():
            if atom_id in self._site.getAtomNumbersList():
                site_atom_position += 1
                #print site_atom_position, atom_id, atom_position, atom_name, molecule.p_atpos[atom_position][:]
                p_atpos[site_atom_position]  = molecule.p_atpos[atom_position]
                p_rad3[site_atom_position]   = molecule.p_rad3[atom_position]
                p_chrgv4[site_atom_position] = self.getCharge(atom_name)
                atinf[site_atom_position].value = molecule.atinf[atom_position].value                
                # quick fix, should be done only once per site
                # TODO: fix ^
                if config.params['pbc_dim'] == 2:
                    p_atpos[site_atom_position][0] += offset_x
                    p_atpos[site_atom_position][1] += offset_y
                    p_atpos[site_atom_position][2] += offset_z
                    if p_atpos[site_atom_position][0] < 0:
                        p_atpos[site_atom_position][0] = box[0] * 10 + p_atpos[site_atom_position][0]
                    if p_atpos[site_atom_position][1] < 0:
                        p_atpos[site_atom_position][1] = box[1] * 10 + p_atpos[site_atom_position][1]

                    p_atpos[site_atom_position][0] = round(p_atpos[site_atom_position][0], 2)
                    p_atpos[site_atom_position][1] = round(p_atpos[site_atom_position][1], 2)
                    p_atpos[site_atom_position][2] = round(p_atpos[site_atom_position][2], 2)

                    #if self._site._res_number == 2769:
                    #    print half_box_xy, site_center
                    #    print p_atpos[site_atom_position][0], p_atpos[site_atom_position][1], p_atpos[site_atom_position][2]
                    #    exit()


                p_chrgv4[site_atom_position] = round(p_chrgv4[site_atom_position], 3)
                p_rad3[site_atom_position] = round(p_rad3[site_atom_position], 3)

                aID = site_atom_position
                aname   = atinf[site_atom_position].value.split()[0]
                resname = atinf[site_atom_position].value.split()[1]
                resnumb = int(atinf[site_atom_position].value.split()[2])
                x = round(p_atpos[site_atom_position][0], 3)
                y = round(p_atpos[site_atom_position][1], 3)
                z = round(p_atpos[site_atom_position][2], 3)
                pdb_text += new_pdb_line(aID, aname, resname, resnumb, x, y, z)

        delphimol.changeStructureSize(self._natoms, p_atpos, p_rad3, p_chrgv4, atinf, p_iatmed)

        if config.params['pbc_dim'] == 2:            
            x = molecule.box[0] * 10 / 2
            y = x
            z = self._site._center[2]
            acent = [x, y, z]
        else:
            acent = self._site._center
        acent = [round(acent[0], 4), round(acent[1], 4), round(acent[2], 3)]

        with open('{1}-{0}.pdb'.format(self._name, self._site._res_number), 'w') as f_new:
            x, y, z = acent
            pdb_text += new_pdb_line(-1, 'P', 'CNT', -1, x, y, z)
            f_new.write(pdb_text)

        return acent

    def add_pbc(self, x, y, z, box, radius, charge, inf, cutoff=5.0):
        box = box * 10    
        x_new = x
        y_new = y
        z_new = z
        inf = '-' + inf[1:]
        charge = 0.0
        new_atoms = []
        if (x < cutoff):
            x_new = box + x
            new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
            if (y < cutoff):
                y_new = box + y
                new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
            elif (y > box - cutoff):
                y_new = y - box
                new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
        elif (x > box - cutoff):
            x_new = x - box
            new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
            if (y < cutoff):
                y_new = box + y
                new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
            elif (y > box - cutoff):
                y_new = y - box
                new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
        x_new = x
        if (y < cutoff):
            y_new = box + y
            new_atoms.append((x_new, y_new, z_new, radius, charge, inf))
        elif (y > box - cutoff):
            y_new = y - box
            new_atoms.append((x_new, y_new, z_new, radius, charge, inf))

        return new_atoms

    # Get Methods
    def getSiteResNumber(self):
        return self._site.getResNumber()

    def getCharge(self, atom_name):
        return self._charge_set[atom_name]

    def getName(self):
        return self._name

    # Print Methods
    def __str__(self):
        out = self._name + '\n'
        for i in self._charge_set.keys():
            out += '{0:>7.3f} {1}\n'.format(self._charge_set[i], i)
        return out

    # Assertion Methods
    def isRefTautomer(self):
        if self == self._site._ref_tautomer:
            return True
        else:
            False

    # Calculation Methods
    def CalcPotentialTautomer(self):
        """Run DelPhi simulation of single site tautomer

        Ensures:
            self._esolvation (float): tautomer solvation energy
            self._p_sitpot (list): potential on site atoms
        """
        if config.debug:
            t0 = time.clock()
            print self._name
            print self._charge_set
        molecule = self._molecule
        delphimol = molecule.getDelPhi()
        acent = self.setDetailsFromTautomer()

        #if self._site._res_number == 770:
        #    exit()

        filename = '{0}_{1}.prm'.format(self._name, self._site._res_number)
        logfile = 'LOG_runDelPhi_{0}_{1}_modelcompound'.format(self._name,
                                                               self._site._res_number)
        #print 'started', self._name, self._site._res_number, 'modelcompound'
        delphimol.runDelPhi(scale=config.params['scaleM'],
                            nonit=0, nlit=config.params['nlit'], relpar=0, relfac=0,
                            acent=acent, pbx=False, pby=False, debug=config.debug,
                            filename=filename,
                            outputfile=logfile)
        #print 'ended', self._name, self._site._res_number, 'modelcompound'

        log.checkDelPhiErrors(logfile)

        self._esolvation = delphimol.getSolvation()
        self._p_sitpot   = delphimol.getSitePotential()
        if config.debug:
            t1 = time.clock() - t0
            filename = '{0}_{1}.profl'.format(self._name, self.getSiteResNumber())
            with open(filename, 'a') as f_new:
                f_new.write('time -> {0:10} {1:10}\n'.format(t0, t1))

        return self._esolvation, self._p_sitpot[:]

    def CalcPotentialTitratingMolecule(self):
        """Run DelPhi simulation of the site tautomer 
        within the whole molecule

        Ensures:
            self._esolvation (float): tautomer solvation energy
            self._p_sitpot (list): potential on site atoms
        """
        if config.debug:
            start = time.clock()
        molecule = self._molecule
        delphimol = molecule.getDelPhi()

        acent = self.setDetailsFromWholeMolecule()

        if config.debug:
            t0 = time.clock() - start

            print self._name, 'starting'
            p_atpos    = delphimol.get_atpos()
            p_rad3   = delphimol.get_rad3()
            p_chrgv4 = delphimol.get_chrgv4()
            atinf    = delphimol.get_atinf()             
            #for atom_name, atom_id, atom_position in molecule.iterAtoms():
            #    print (atinf[atom_position].value, p_chrgv4[atom_position], p_rad3[atom_position],
            #           p_atpos[atom_position][0], p_atpos[atom_position][1], p_atpos[atom_position][2])

        filename = '{0}_{1}.prm'.format(self._name, self._site._res_number)
        logfile = 'LOG_runDelPhi_{0}_{1}_wholeprotein'.format(self._name,
                                                              self._site._res_number)

        #print 'started', self._name, self._site._res_number, 'wholeprotein'
        if config.params['pbc_dim'] == 2:
            delphimol.runDelPhi(scale_prefocus=config.params['scaleP'],
                                scale=config.params['scaleM'],
                                nlit_prefocus=config.params['nlit'],
                                nonit=config.params['nonit'],
                                nlit=500, acent=acent, nonit_focus=0,
                                relfac_focus=0.0, relpar_focus=0.0,
                                relpar=config.params['relpar'],
                                relfac=config.params['relfac'],
                                pbx=config.params['pbx'],
                                pby=config.params['pby'], pbx_focus=False,
                                pby_focus=False, debug=config.debug,
                                filename=filename,
                                outputfile=logfile)
        else:
            delphimol.runDelPhi(scale=config.params['scaleP'],
                                nonit=0, nlit=config.params['nlit'],
                                relpar=0, relfac=0,
                                acent=acent, pbx=False, pby=False,                                
                                debug=config.debug,
                                filename=filename,
                                outputfile=logfile)
        #print 'ended', self._name, self._site._res_number, 'wholeprotein'
        log.checkDelPhiErrors(logfile)
        
        fname = 'P_{1}-{0}.out'.format(self._name, self._site._res_number)

        self._esolvation = delphimol.getSolvation()
        self._p_sitpot   = delphimol.getSitePotential()

        if config.debug:
            with open('{0}_{1}.frc'.format(self._name, self._site._res_number), 'w') as f:
                text = ''
                for atom_name, atom_id, atom_position in molecule.iterAtoms():
                    text += '{0} {1} {2} {3} {4} {5} {6}\n'.format(atinf[atom_position].value, round(p_chrgv4[atom_position], 3), round(p_rad3[atom_position], 4), round(p_atpos[atom_position][0], 3), round(p_atpos[atom_position][1], 3), round(p_atpos[atom_position][2], 3), self._p_sitpot[atom_position])
                f.write(text)


        if config.debug:
            t1 = time.clock() - start
            filename = '{0}_{1}.profl'.format(self._name, self.getSiteResNumber())
            with open(filename, 'a') as f_new:
                f_new.write('time -> {0:10}     {1:10}\n'.format(t0, t1))

            print self._esolvation, self._name

        return self._esolvation, self._p_sitpot[:]

    def calcBackEnergy(self):
        """Calculates background energy contribution"""
        if config.debug:
            print self._name, 'background energy start'
        molecule = self._molecule
        text = ''
        distance = -999999
        cutoff = copy(config.params['cutoff'])
        cutoff2 = (cutoff * 10) ** 2
        point_energy = -1
        for atom_name, atom_id, atom_position in molecule.iterAtoms():
            if atom_id not in self._site.getAtomNumbersList():
                if cutoff != -1:
                    distance = self.distance_to(molecule.p_atpos[atom_position])
                if cutoff != -1 or distance <= cutoff2:                    
                    point_energy = round(molecule.p_chrgv4[atom_position], 3) * round(self._sitpotM[atom_position], 4)
                    self._e_back += point_energy
                    if config.debug:
                        point_energy = round(molecule.p_chrgv4[atom_position], 3) * round(self._sitpotM[atom_position], 4)
                        text += '{} {} {} {} {} {} {} {}\n'.format(atom_name, atom_id, point_energy, molecule.p_chrgv4[atom_position], self._sitpotM[atom_position], molecule.p_atpos[atom_position][:], distance, cutoff2)

        if config.debug:
            with open('{0}_{1}_eback.xvg'.format(self._name, self._site._res_number), 'w') as f_new:
                text += str(self._e_back / config.log10)
                f_new.write(text)

            print 'e_back finished'

    def calcpKint(self):
        """Calculates the pKint of the tautomer"""
        ref_taut = self._site._ref_tautomer

        dG_solvationM = ref_taut._esolvationM - self._esolvationM
        dG_solvationS = ref_taut._esolvationS - self._esolvationS
        dG_back       = ref_taut._e_back - self._e_back

        dG_solvationM /= config.log10
        dG_solvationS /= config.log10 
        dG_back       /= config.log10

        if self._site.getType() == 'a':
            pKint = self._pKmod + (dG_solvationM - dG_solvationS + dG_back)
            chargediff = -1
        elif self._site.getType() == 'c':
            pKint = self._pKmod - (dG_solvationM - dG_solvationS + dG_back)
            chargediff = 1            
        else:
            raise Exception('Site files were poorly interpreted')

        dg = pKint * config.log10 * config.kBoltz * float(config.params['temp']) * chargediff
        if config.debug:
            print 'pKint ->', self._name, pKint, dg
        self.pKint = pKint
        self.dG_solvationM = dG_solvationM
        self.dG_solvationS = dG_solvationS
        self.dG_back = dG_back
        self._dg = dg

    def calcInteractionWith(self, tautomer2, site_atom_list, iterAtomsList):
        """Calculates the interaction energy 
        between self tautomer and tautomer2

        Args:
            tautomer2 (Tautomer)
            site_atom_list (list): atom numbers belonging to the site
            iterAtomsList (list): details on the titrating molecule atoms
        """
        molecule = self._molecule
        interaction = 0.0
        tau2_ref = tautomer2._site._ref_tautomer
        for atom_name, atom_id, atom_position in iterAtomsList:
            if atom_id in site_atom_list:
                charge_ref = molecule.p_chrgv4[atom_position]
                charge_tau = self.getCharge(atom_name)
                charge = round(charge_ref, 3) - round(charge_tau, 3)

                potential_ref = tau2_ref._sitpotM[atom_position]
                potential_tau2 = tautomer2._sitpotM[atom_position]
                potential = round(potential_ref, 4) - round(potential_tau2, 4)

                interaction += charge * potential

                if ((self._name == 'AS0' and tautomer2._name == 'CT0') or \
                    (tautomer2._name == 'AS0' and self._name == 'CT0')) and \
                    (self._site._res_number == 18 and tautomer2._site._res_number == 2129 or \
                     tautomer2._site._res_number == 18 and self._site._res_number == 2129):
                    print 'exit->->', charge_ref, charge_tau, potential_ref, potential_tau2, atom_id



        site1_chrgtyp = self._site.getRefProtState()
        site2_chrgtyp = tautomer2._site.getRefProtState()

        dG_interaction = site1_chrgtyp * site2_chrgtyp
        dG_interaction *= abs(interaction * config.kBoltz * float(config.params['temp']))

        return dG_interaction

    def distance_to(self, atom_position):
        center = self._site.getCenterH()

        dx = abs(center[0] - atom_position[0])
        dy = abs(center[1] - atom_position[1])
        dz = abs(center[2] - atom_position[2])

        box = [i * 10 for i in self._molecule.box]
        #print center, atom_position[:], box
        if dx > box[0] / 2 :
            dx = abs(dx - box[0])
        if dy > box[1] / 2 :
            dy = abs(dy - box[1])
        #print dx, dy, dz, dx ** 2 + dy ** 2 + dz ** 2
        #exit()
        return dx ** 2 + dy ** 2 + dz ** 2

