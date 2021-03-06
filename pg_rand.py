# This file is part of the master thesis "Variational crimes in the Localized orthogonal decomposition method":
#   https://github.com/TiKeil/Masterthesis-LOD.git
# Copyright holder: Tim Keil 
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)
# This file is motivated by gridlod: https://github.com/TiKeil/gridlod.git

import numpy as np
from copy import deepcopy
import scipy.sparse as sparse

from gridlod import lod, util, fem, ecworker, eccontroller

class VcPetrovGalerkinLOD:
    def __init__(self, origincoef, world, k, IPatchGenerator, printLevel=0):
        self.world = world
        NtCoarse = np.prod(world.NWorldCoarse)
        self.k = k
        self.IPatchGenerator = IPatchGenerator
        self.printLevel = printLevel
                
        self.epsilonList = None
        self.ageList = None
        
        #origin correctors and rhs correctors
        self.ecList = None
        self.ecListtesting = None
        self.ecListOrigin = None
        self.rhsCList = None
        self.rhsCListOrigin = None
        self.Kms = None
        self.Rms = None
        self.K = None
        self.basisCorrectors = None
        
        #for testing
        self.currentTestingCorrector = None
        #coefficient without defects
        self.origincoef = origincoef
        
        eccontroller.clearWorkers()
        
    def originCorrectors(self, clearFineQuantities=True):
        world = self.world
        k = self.k
        IPatchGenerator = self.IPatchGenerator
        coefficient = self.origincoef
        
        NtCoarse = np.prod(world.NWorldCoarse)

        saddleSolver = lod.schurComplementSolver(world.NWorldCoarse*world.NCoarseElement)

        # Reset all caches
        self.Kms = None
        self.K = None
        self.basisCorrectors = None
        
        self.ecListOrigin = [None]*NtCoarse
        
        if self.printLevel >= 2:
            print 'Setting up workers for origin Correctors'
        eccontroller.setupWorker(world, coefficient, IPatchGenerator, k, clearFineQuantities, self.printLevel)
        if self.printLevel >= 2:
            print 'Done'
        
        #element corrector list has coarse element size 
        ecListOrigin = self.ecListOrigin     
        ecComputeList = []
                
        for TInd in range(NtCoarse):
            #TInd is one coarse element    
            
            #mapper
            iElement = util.convertpIndexToCoordinate(world.NWorldCoarse-1, TInd)
                
            ecComputeList.append((TInd, iElement))    
        
        if self.printLevel >= 2:
            print 'Waiting for results', len(ecComputeList)
                    
        ecResultList = eccontroller.mapComputations(ecComputeList, self.printLevel)
        for ecResult, ecCompute in zip(ecResultList, ecComputeList):
            ecListOrigin[ecCompute[0]] = ecResult
            
        self.ecList = deepcopy(ecListOrigin)
        self.ecListtesting = deepcopy(ecListOrigin)

    def CorrectorsToOrigin(self):
        self.ecListtesting = self.ecListOrigin
    
    def originRhsCorrectors(self, clearFineQuantities=True):
        '''
        todo update to ecworkers
        '''
        
        world = self.world
        k = self.k
        IPatchGenerator = self.IPatchGenerator
        coefficient = self.origincoef
        
        NtCoarse = np.prod(world.NWorldCoarse)

        saddleSolver = lod.schurComplementSolver(world.NWorldCoarse*world.NCoarseElement)
    
        # Reset all caches take care
        # self.Rms = None
        # self.R = None
        # self.basisCorrectors = None
        
        self.rhsCListOrigin = [None]*NtCoarse
        
        #element corrector list has coarse element size 
        rhsCListOrigin = self.rhsCListOrigin     
                
        for TInd in range(NtCoarse):
            #TInd is one coarse element    
            iElement = util.convertpIndexToCoordinate(world.NWorldCoarse-1, TInd)
            
            if rhsCListOrigin[TInd] is not None:
                rhsCT = rhsCListOrigin[TInd]
                if hasattr(coefficient, 'rCoarse'):
                    coefficientPatch = coefficient.localize(rhsCT.iPatchWorldCoarse, rhsCT.NPatchCoarse)
                elif hasattr(rhsCT, 'fsi'):
                    coefficientPatch = coefficient.localize(rhsCT.iPatchWorldCoarse, rhsCT.NPatchCoarse)
                else:
                    coefficientPatch = None
            else:
                coefficientPatch = None
    
            rhsCT = lod.elementCorrector(world, k, iElement, saddleSolver)
            
            if coefficientPatch is None:
                coefficientPatch = coefficient.localize(rhsCT.iPatchWorldCoarse, rhsCT.NPatchCoarse)
            IPatch = IPatchGenerator(rhsCT.iPatchWorldCoarse, rhsCT.NPatchCoarse)
                    
            rhsCT.computeRhsCorrectors(coefficientPatch, IPatch)
            rhsCT.computeRhsCoarseQuantities()
            if clearFineQuantities:
                rhsCT.clearFineQuantities()
            rhsCListOrigin[TInd] = rhsCT
            
        self.rhsCList = deepcopy(rhsCListOrigin)

            
    def updateCorrectors(self, coefficient, epsilonTol, f, epsilonQuestion =0, clearFineQuantities=True, Testing = None, Computing= True,mc=0):
        assert(self.ecListOrigin is not None)
        
        if epsilonTol == 0 and Computing == True and mc==0:
            self.printLevel = 2
            
        world = self.world
        k = self.k
        IPatchGenerator = self.IPatchGenerator
        
        NtCoarse = np.prod(world.NWorldCoarse)

        saddleSolver = lod.schurComplementSolver(world.NWorldCoarse*world.NCoarseElement)
        
        # Reset all caches
        self.Kms = None
        self.K = None
        self.basisCorrectors = None
                
        
        self.ageList = [0]*NtCoarse
        
        if self.epsilonList == None:
            self.epsilonList = [np.nan]*NtCoarse
        
        #element corrector list has coarse element size 
        if Testing:
            ecListOrigin = self.ecListtesting
        else:
            ecListOrigin = self.ecListOrigin
        
        ecList = deepcopy(ecListOrigin)
        
        if self.printLevel >= 2:
            print 'Setting up workers'
        eccontroller.setupWorker(world, coefficient, IPatchGenerator, k, clearFineQuantities, self.printLevel)
        if self.printLevel >= 2:
            print 'Done'
        
        #only for coarse coefficient
        if self.ecList is not None and hasattr(coefficient, 'rCoarse'):
            ANew = coefficient._aBase
            AOld = deepcopy(self.origincoef.aFine)
            delta = np.abs((AOld-ANew)/np.sqrt(AOld*ANew))
            ceta = np.abs(AOld/ANew)
        
        # saves the age of the corrector and error indicator for element
        ageList = self.ageList
        
        if epsilonTol == 0:
            epsilonList = self.epsilonList
        else:
            epsilonList = deepcopy(self.epsilonList)
        
        recomputeCount = 0
        ecComputeList = []
        for TInd in range(NtCoarse):
            if self.printLevel >= 3:
                print str(TInd) + ' / ' + str(NtCoarse),
            
            ageList[TInd] += 1
            
            #mapper
            iElement = util.convertpIndexToCoordinate(world.NWorldCoarse-1, TInd)
            ecT = ecListOrigin[TInd]
            if Testing:
                epsilonT = epsilonList[TInd]
            else:    
                if hasattr(coefficient, 'aLagging'):
                    coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
                    epsilonT = ecList[TInd].computeErrorIndicatorFineWithLagging(coefficientPatch.aFine, coefficientPatch.aLagging)
                if hasattr(coefficient, 'rCoarse'):
                    coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
                    epsilonT = ecListOrigin[TInd].computeTimsCoarseErrorIndicator(delta,ceta)
                elif hasattr(ecT, 'fsi'):
                    coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
                    epsilonT = ecListOrigin[TInd].computeErrorIndicatorFine(coefficientPatch)
                epsilonList[TInd] = epsilonT
            
            if self.printLevel >= 2:
                print 'epsilonT = ' + str(epsilonT), 
                
            if epsilonT > epsilonTol:
                if self.printLevel >= 2:
                    print 'C'
                if Testing:
                    epsilonList[TInd] = 0
                    self.currentTestingCorrector = TInd
                ecComputeList.append((TInd, iElement))
                ecList[TInd] = None
                ageList[TInd] = 0
                recomputeCount += 1
            else:
                if self.printLevel > 1:
                    print 'N'    
        
        if self.printLevel >= 2:
            print 'Waiting for results', len(ecComputeList)
        
        if self.printLevel > 0 or Testing:
            if mc == 0:
                print "To be recomputed: ", float(recomputeCount)/NtCoarse*100, '%'
        
        self.printLevel = 0

        if Computing:
            ecResultList = eccontroller.mapComputations(ecComputeList, self.printLevel)
            for ecResult, ecCompute in zip(ecResultList, ecComputeList):
                ecList[ecCompute[0]] = ecResult
        else:
            print "Not Recomputed!"
                
        self.ecList = ecList
        
        if epsilonTol != 0:
            self.ecListtesting = ecList
        
        if Testing:
            self.epsilonList = epsilonList    
            
        ageListinv = np.ones(np.size(ageList))
        ageListinv = ageListinv - ageList
        
        if epsilonQuestion == 0:
            return ageListinv
        
        if epsilonQuestion == 1:
            return ageListinv, epsilonList

    def ErrorIndicator(self, coefficient):
        assert(self.ecListOrigin is not None)
        
        world = self.world
        k = self.k
        IPatchGenerator = self.IPatchGenerator
        
        NtCoarse = np.prod(world.NWorldCoarse)

        saddleSolver = lod.schurComplementSolver(world.NWorldCoarse*world.NCoarseElement)
                
        self.epsilonList = [np.nan]*NtCoarse
        
        #element corrector list has coarse element size 
        ecListOrigin = self.ecListOrigin
        ecList = deepcopy(ecListOrigin)     
                
        epsilonList = self.epsilonList
        
        for TInd in range(NtCoarse):
            #TInd is one coarse element
            iElement = util.convertpIndexToCoordinate(world.NWorldCoarse-1, TInd)
            
            ecT = ecListOrigin[TInd]
            if hasattr(coefficient, 'rCoarse'):
                coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
                epsilonT = ecListOrigin[TInd].computeTimsCoarseErrorIndicator(delta,ceta)
            elif hasattr(ecT, 'fsi'):
                coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
                epsilonT = ecListOrigin[TInd].computeErrorIndicatorFine(coefficientPatch)

            epsilonList[TInd] = epsilonT
            
        return epsilonList        

    def clearCorrectors(self):
        NtCoarse = np.prod(self.world.NWorldCoarse)
        self.ecList = None
        self.coefficient = None

    def computeCorrection(self, ARhsFull=None, MRhsFull=None):
        assert(self.ecList is not None)
        assert(self.origincoef is not None)

        world = self.world
        NCoarseElement = world.NCoarseElement
        NWorldCoarse = world.NWorldCoarse
        NWorldFine = NWorldCoarse*NCoarseElement

        NpFine = np.prod(NWorldFine+1)
        
        coefficient = self.origincoef
        IPatchGenerator = self.IPatchGenerator

        localBasis = world.localBasis
        
        TpIndexMap = util.lowerLeftpIndexMap(NCoarseElement, NWorldFine)
        TpStartIndices = util.pIndexMap(NWorldCoarse-1, NWorldFine, NCoarseElement)
        
        uFine = np.zeros(NpFine)
        
        NtCoarse = np.prod(world.NWorldCoarse)
        for TInd in range(NtCoarse):
            if self.printLevel > 0:
                print str(TInd) + ' / ' + str(NtCoarse)
                
            ecT = self.ecList[TInd]
            
            coefficientPatch = coefficient.localize(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)
            IPatch = IPatchGenerator(ecT.iPatchWorldCoarse, ecT.NPatchCoarse)

            if ARhsFull is not None:
                ARhsList = [ARhsFull[TpStartIndices[TInd] + TpIndexMap]]
            else:
                ARhsList = None
                
            if MRhsFull is not None:
                MRhsList = [MRhsFull[TpStartIndices[TInd] + TpIndexMap]]
            else:
                MRhsList = None
                
            correctorT = ecT.computeElementCorrector(coefficientPatch, IPatch, ARhsList, MRhsList)[0]
            
            NPatchFine = ecT.NPatchCoarse*NCoarseElement
            iPatchWorldFine = ecT.iPatchWorldCoarse*NCoarseElement
            patchpIndexMap = util.lowerLeftpIndexMap(NPatchFine, NWorldFine)
            patchpStartIndex = util.convertpCoordinateToIndex(NWorldFine, iPatchWorldFine)

            uFine[patchpStartIndex + patchpIndexMap] += correctorT

        return uFine
    
    def assembleBasisCorrectors(self):
        if self.basisCorrectors is not None:
            return self.basisCorrectors

        assert(self.ecList is not None)

        world = self.world
        NWorldCoarse = world.NWorldCoarse
        NCoarseElement = world.NCoarseElement
        NWorldFine = NWorldCoarse*NCoarseElement
        
        NtCoarse = np.prod(NWorldCoarse)
        NpCoarse = np.prod(NWorldCoarse+1)
        NpFine = np.prod(NWorldFine+1)
        
        TpIndexMap = util.lowerLeftpIndexMap(np.ones_like(NWorldCoarse), NWorldCoarse)
        TpStartIndices = util.lowerLeftpIndexMap(NWorldCoarse-1, NWorldCoarse)
        
        cols = []
        rows = []
        data = []
        ecList = self.ecList
        for TInd in range(NtCoarse):
            ecT = ecList[TInd]
            assert(ecT is not None)
            assert(hasattr(ecT, 'fsi'))
            
            NPatchFine = ecT.NPatchCoarse*NCoarseElement
            iPatchWorldFine = ecT.iPatchWorldCoarse*NCoarseElement
            
            patchpIndexMap = util.lowerLeftpIndexMap(NPatchFine, NWorldFine)
            patchpStartIndex = util.convertpCoordinateToIndex(NWorldFine, iPatchWorldFine)
            
            colsT = TpStartIndices[TInd] + TpIndexMap
            rowsT = patchpStartIndex + patchpIndexMap
            dataT = np.hstack(ecT.fsi.correctorsList)
            
            cols.extend(np.repeat(colsT, np.size(rowsT)))
            rows.extend(np.tile(rowsT, np.size(colsT)))
            data.extend(dataT)
        
        basisCorrectors = sparse.csc_matrix((data, (rows, cols)), shape=(NpFine, NpCoarse))

        self.basisCorrectors = basisCorrectors
        return basisCorrectors
    
    def assembleBasisCorrectorsFast(self):
        ''' Is that even possible '''
        if self.basisCorrectors is not None:
            return self.basisCorrectors

        assert(self.ecList is not None)

        world = self.world
        NWorldCoarse = world.NWorldCoarse
        NCoarseElement = world.NCoarseElement
        NWorldFine = NWorldCoarse*NCoarseElement
        
        NtCoarse = np.prod(NWorldCoarse)
        NpCoarse = np.prod(NWorldCoarse+1)
        NpFine = np.prod(NWorldFine+1)
        
        TpIndexMap = util.lowerLeftpIndexMap(np.ones_like(NWorldCoarse), NWorldCoarse)
        TpStartIndices = util.lowerLeftpIndexMap(NWorldCoarse-1, NWorldCoarse)
        
        cols = []
        rows = []
        data = []
        ecList = self.ecList
        for TInd in range(NtCoarse):
            ecT = ecList[TInd]
            assert(ecT is not None)
            assert(hasattr(ecT, 'fsi'))

            NPatchFine = ecT.NPatchCoarse*NCoarseElement
            iPatchWorldFine = ecT.iPatchWorldCoarse*NCoarseElement
            
            patchpIndexMap = util.lowerLeftpIndexMap(NPatchFine, NWorldFine)
            patchpStartIndex = util.convertpCoordinateToIndex(NWorldFine, iPatchWorldFine)
            
            colsT = TpStartIndices[TInd] + TpIndexMap
            rowsT = patchpStartIndex + patchpIndexMap
            dataT = np.hstack(ecT.fsi.correctorsList)

            cols.extend(np.repeat(colsT, np.size(rowsT)))
            rows.extend(np.tile(rowsT, np.size(colsT)))
            data.extend(dataT)

        basisCorrectors = sparse.csc_matrix((data, (rows, cols)), shape=(NpFine, NpCoarse))

        self.basisCorrectors = basisCorrectors
        return basisCorrectors


        
    def assembleMsStiffnessMatrix(self):
        if self.Kms is not None:
            return self.Kms

        assert(self.ecList is not None)

        world = self.world
        NWorldCoarse = world.NWorldCoarse
        
        NtCoarse = np.prod(world.NWorldCoarse)
        NpCoarse = np.prod(world.NWorldCoarse+1)
        
        TpIndexMap = util.lowerLeftpIndexMap(np.ones_like(NWorldCoarse), NWorldCoarse)
        TpStartIndices = util.lowerLeftpIndexMap(NWorldCoarse-1, NWorldCoarse)

        cols = []
        rows = []
        data = []
        ecList = self.ecList
        for TInd in range(NtCoarse):
            ecT = ecList[TInd]
            assert(ecT is not None)

            NPatchCoarse = ecT.NPatchCoarse

            patchpIndexMap = util.lowerLeftpIndexMap(NPatchCoarse, NWorldCoarse)
            patchpStartIndex = util.convertpCoordinateToIndex(NWorldCoarse, ecT.iPatchWorldCoarse)
            
            colsT = TpStartIndices[TInd] + TpIndexMap
            rowsT = patchpStartIndex + patchpIndexMap
            dataT = ecT.csi.Kmsij.flatten()

            cols.extend(np.tile(colsT, np.size(rowsT)))
            rows.extend(np.repeat(rowsT, np.size(colsT)))
            data.extend(dataT)

        Kms = sparse.csc_matrix((data, (rows, cols)), shape=(NpCoarse, NpCoarse))

        self.Kms = Kms
        return Kms
        
    def assembleMsRhsMatrix(self):
        if self.Rms is not None:
            return self.Rms

        assert(self.rhsCList is not None)

        world = self.world
        NWorldCoarse = world.NWorldCoarse
        
        NtCoarse = np.prod(world.NWorldCoarse)
        NpCoarse = np.prod(world.NWorldCoarse+1)
        
        TpIndexMap = util.lowerLeftpIndexMap(np.ones_like(NWorldCoarse), NWorldCoarse)
        TpStartIndices = util.lowerLeftpIndexMap(NWorldCoarse-1, NWorldCoarse)

        cols = []
        rows = []
        data = []
        ecList = self.rhsCList
        for TInd in range(NtCoarse):
            ecT = ecList[TInd]
            assert(ecT is not None)

            NPatchCoarse = ecT.NPatchCoarse

            patchpIndexMap = util.lowerLeftpIndexMap(NPatchCoarse, NWorldCoarse)
            patchpStartIndex = util.convertpCoordinateToIndex(NWorldCoarse, ecT.iPatchWorldCoarse)
            
            colsT = TpStartIndices[TInd] + TpIndexMap
            rowsT = patchpStartIndex + patchpIndexMap
            dataT = ecT.csi.Rmsij.flatten()

            cols.extend(np.tile(colsT, np.size(rowsT)))
            rows.extend(np.repeat(rowsT, np.size(colsT)))
            data.extend(dataT)

        Rms = sparse.csc_matrix((data, (rows, cols)), shape=(NpCoarse, NpCoarse))

        self.Rms = Rms
        return Rms


    def assembleStiffnessMatrix(self):
        if self.K is not None:
            return self.K

        assert(self.ecList is not None)

        world = self.world
        NWorldCoarse = world.NWorldCoarse
        
        NtCoarse = np.prod(world.NWorldCoarse)
        NpCoarse = np.prod(world.NWorldCoarse+1)
        
        TpIndexMap = util.lowerLeftpIndexMap(np.ones_like(NWorldCoarse), NWorldCoarse)
        TpStartIndices = util.lowerLeftpIndexMap(NWorldCoarse-1, NWorldCoarse)

        cols = []
        rows = []
        data = []
        ecList = self.ecList
        for TInd in range(NtCoarse):
            ecT = ecList[TInd]
            assert(ecT is not None)

            NPatchCoarse = ecT.NPatchCoarse

            colsT = TpStartIndices[TInd] + TpIndexMap
            rowsT = TpStartIndices[TInd] + TpIndexMap
            dataT = ecT.csi.Kij.flatten()

            cols.extend(np.tile(colsT, np.size(rowsT)))
            rows.extend(np.repeat(rowsT, np.size(colsT)))
            data.extend(dataT)

        K = sparse.csc_matrix((data, (rows, cols)), shape=(NpCoarse, NpCoarse))

        self.K = K
        return K
    