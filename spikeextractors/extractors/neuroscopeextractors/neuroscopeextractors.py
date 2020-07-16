from spikeextractors import RecordingExtractor,SortingExtractor,MultiSortingExtractor
from spikeextractors.extractors.bindatrecordingextractor import BinDatRecordingExtractor
import numpy as np
from pathlib import Path
from spikeextractors.extraction_tools import check_get_traces_args,check_valid_unit_id,read_binary
from bs4 import BeautifulSoup
import os

from os import listdir
from os.path import isfile, join

try:
    import bs4
    import lxml
    HAVE_BS4_LXML = True
except ImportError:
    HAVE_BS4_LXML = False

class NeuroscopeRecordingExtractor(BinDatRecordingExtractor):
    
    """
    Extracts raw neural recordings from large binary .dat files in the neuroscope format.
    
    The recording extractor always returns channel IDs starting from 0.
    
    The recording data will always be returned in the shape of (num_channels,num_frames).

    Parameters
    ----------
    folder_path : str
        Path to the folder containing the .dat file.
    """
    extractor_name = 'NeuroscopeRecordingExtractor'
    installed = True  # check at class level if installed or not
    is_writable = True
    mode = 'folder'
    installation_mesg = 'please install bs4 and lxml to use this extractor'  # error message when not installed
            
    def __init__(self, folder_path, subset_channels=None):
        assert HAVE_BS4_LXML, self.installation_mesg
        RecordingExtractor.__init__(self)
        self._recording_file = folder_path
        
        fpath_base, fname = os.path.split(folder_path)
        xml_filepath = os.path.join(folder_path, fname + '.xml')
        dat_filepath = os.path.join(folder_path, fname + '.dat')
        
        with open(xml_filepath, 'r') as xml_file:
            contents = xml_file.read()
            soup = BeautifulSoup(contents, 'lxml')
            # Normally, this would be a .xml, but there were strange issues
            # in the write_recording method that require it to be a .lxml instead
            # which also requires all capital letters to be removed from the tag names
        
        n_bits = int(soup.nbits.string)
        dtype='int'+str(n_bits)
        num_channels = int(soup.nchannels.string)
        
        if subset_channels is not None:
            num_channels = len(subset_channels)
        
        sampling_frequency = float(soup.samplingrate.string)
        
        BinDatRecordingExtractor.__init__(self, dat_filepath, sampling_frequency=sampling_frequency,
                                          dtype=dtype, numchan=num_channels)
        
        self._kwargs = {'folder_path': str(Path(folder_path).absolute()),
                        'subset_channels': subset_channels}
        
        
    @staticmethod
    def write_recording(recording, save_path, dtype='int32'):
        """ Convert and save the recording extractor to Neuroscope format

        parameters
        ----------
        recording: RecordingExtractor
            The recording extractor to be converted and saved
        save_path: str
            Full path to desired target folder
        dtype: str
            Data type to be used in writing. Will throw a warning if stored recording type from get_traces() does not match.
        """
        _, RECORDING_NAME = os.path.split(save_path)
        save_xml = "{}/{}.xml".format(save_path,RECORDING_NAME)

        # write recording
        recording_fn = os.path.join(save_path, RECORDING_NAME)

        # create parameters file if none exists
        if not os.path.isfile(save_xml):
            soup = BeautifulSoup("",'xml')

            new_tag = soup.new_tag('nbits')
            dtype = recording.get_dtype()
            
            if not any([dtype == x for x in ['int16', 'int32']]):
                print('Warning: Unsupported data type passed (',dtype,'); converting to default of int32!',sep="")
                dtype = 'int32'
                
            n_bits = str(dtype)[3:5]
            new_tag.string = str(n_bits)
            soup.append(new_tag)

            new_tag = soup.new_tag('nchannels')
            new_tag.string = str(len(recording.get_channel_ids()))
            soup.append(new_tag)

            new_tag = soup.new_tag('samplingrate')
            new_tag.string = str(recording.get_sampling_frequency())
            soup.append(new_tag)

            # write parameters file
            f = open(save_xml, "w")
            f.write(str(soup))
            f.close()
            
        BinDatRecordingExtractor.write_recording(recording, recording_fn, dtype=dtype)
        

class NeuroscopeSortingExtractor(SortingExtractor):

    """
    Extracts spiking information from pair of .res and .clu files. The .res is a text file with
    a sorted list of all spiketimes from all units displayed in sample (integer '%i') units.
    The .clu file is a file with one more row than the .res with the first row corresponding to
    the total number of unique ids in the file (and may exclude 0 & 1 from this count)
    with the rest of the rows indicating which unit id the corresponding entry in the
    .res file refers to.
    
    In the original Neuroscope format:
        Unit ID 0 is the cluster of unsorted spikes (noise).
        Unit ID 1 is a cluster of multi-unit spikes.
        
    The function defaults to returning multi-unit activity as the first index, and ignoring unsorted noise.
    To return only the fully sorted units, set keep_mua_units=False.
        
    The sorting extractor always returns unit IDs from 1, ..., number of chosen clusters.

    Parameters
    ----------
    resfile_path : str
        Optional. Path to a particular .res text file.
    clufile_path : str
        Optional. Path to a particular of .clu text file.
    folder_path : str
        Optional. Path to the collection of .res and .clu text files. Will auto-detect format.
    keep_mua_units : bool
        Optional. Whether or not to return sorted spikes from multi-unit activity. Defaults to True.
    """
    extractor_name = 'NeuroscopeSortingExtractor'
    installed = True  # check at class level if installed or not
    is_writable = True
    mode = 'custom'
    installation_mesg = ""  # error message when not installed

    def __init__(self, resfile_path=None, clufile_path=None, folder_path=None, keep_mua_units=True):
        SortingExtractor.__init__(self)
        
        # None of the location arguments were passed
        assert not (folder_path is None and resfile_path is None and clufile_path is None), 'Either pass a single folder_path location, or a pair of resfile_path and clufile_path. None received.'
      
        # At least one passed
        if resfile_path is not None or clufile_path is not None:
            assert resfile_path is not None and clufile_path is not None, 'If passing resfile_path or clufile_path, both are required.'
        
            # If all three file paths were passed, throw warning but override folder_path anyway
            if folder_path is not None:
                print('Warning: Pass either a single folder_path location, or a pair of resfile_path and clufile_path. Ignoring passed folder_path.')
            
            folder_path, _ = os.path.split(resfile_path)
            
        _, SORTING_NAME = os.path.split(folder_path)
        xml_filepath = "{}/{}.xml".format(folder_path,SORTING_NAME)
        
        with open(xml_filepath, 'r') as xml_file:
            contents = xml_file.read()
            soup = BeautifulSoup(contents, 'lxml')
            # Normally, this would be a .xml, but there were strange issues
            # in the write_recording method that require it to be a .lxml instead
            # which also requires all capital letters to be removed from the tag names
        
        self._sampling_frequency = float(soup.samplingrate.string) # careful not to confuse it with the lfpsamplingsate
        
        # Classic functionality reading only a single pair of res and clu files
        if resfile_path is not None and clufile_path is not None:
            res = np.loadtxt(resfile_path, dtype=np.int64, usecols=0, ndmin=1)
            clu = np.loadtxt(clufile_path, dtype=np.int64, usecols=0, ndmin=1)
            if len(res) > 0:
                # Extract the number of clusters read as the first line of the clufile then remove it from the clu list
                n_clu = clu[0]
                clu = np.delete(clu, 0)
                unique_ids = np.unique(clu)

                if not unique_ids==np.arange(n_clu+1): # some missing IDs somewhere
                    if 0 not in unique_ids: # missing unsorted IDs
                        n_clu += 1
                    if 1 not in unique_ids: # missing mua IDs
                        n_clu += 1
                    # If it is any other ID, then it would be very strange if it were missing...

                # Initialize spike trains and extract times from .res and appropriate clusters from .clu based on user input for ignoring multi-unit activity
                self._spiketrains = []
                if keep_mua_units: # default
                    n_clu -= 1;
                    self._unit_ids = [x+1 for x in range(n_clu)] # generates list from 1,...,clu[0]-1
                    for s_id in self._unit_ids:
                        self._spiketrains.append(res[(clu == s_id).nonzero()])
                else:
                    # Ignoring IDs of 0 until get_unsorted_spike_train is implemented into base
                    # Also ignoring IDs of 1 since user called keep_mua_units=False
                    n_clu -= 2;
                    self._unit_ids = [x+1 for x in range(n_clu)] # generates list from 1,...,clu[0]-2
                    for s_id in self._unit_ids:
                        self._spiketrains.append(res[(clu == s_id+1).nonzero()]) # only reading cluster IDs 2,...,clu[0]-1
                        
        elif resfile_path is None and clufile_path is None:
            # Auto-detects files from general_path
            onlyfiles = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]
            
            end_res = [x[-3:]=='res' for x in onlyfiles]
            end_clu = [x[-3:]=='clu' for x in onlyfiles]
            any_res = any(end_res)
            any_clu = any(end_clu)
            
            if any_res or any_clu:
                assert any_res == True and any_clu == True, 'Unmatched .res and .clu files detected!'
                
                resfile_path = '{}/{}.res'.format(folder_path,SORTING_NAME)
                clufile_path = '{}/{}.clu'.format(folder_path,SORTING_NAME)
                
                NeuroscopeSortingExtractor.__init__(self, resfile_path=resfile_path,
                                                          clufile_path=clufile_path,
                                                          keep_mua_units=keep_mua_units)

        else:
            self._spiketrains = []
            self._unit_ids = []
             
            
        self._kwargs = {'resfile_path': str(Path(resfile_path).absolute()),
                        'clufile_path': str(Path(clufile_path).absolute()),
                        'folder_path': str(Path(folder_path).absolute()),
                        'keep_mua_units': keep_mua_units}


    def get_unit_ids(self):
        return list(self._unit_ids)
    
    
    def get_sampling_frequency(self):
        return self._sampling_frequency
    
    
    def shift_unit_ids(self,shift):
        self._unit_ids = [x + shift for x in self._unit_ids]
    
    
    def add_unit(self, unit_id, spike_times):
        '''This function adds a new unit with the given spike times.

        Parameters
        ----------
        unit_id: int
            The unit_id of the unit to be added.
        '''
        self._unit_ids.append(unit_id)
        self._spiketrains.append(spike_times)
    

    @check_valid_unit_id
    def get_unit_spike_train(self, unit_id, shank_id=None, start_frame=None, end_frame=None):
        start_frame, end_frame = self._cast_start_end_frame(start_frame, end_frame)
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = np.Inf
        times = self._spiketrains[self.get_unit_ids().index(unit_id)]
        inds = np.where((start_frame <= times) & (times < end_frame))
        return times[inds]

    
    @staticmethod
    def write_sorting(sorting, save_path):
        _, SORTING_NAME = os.path.split(save_path)
            
        # Create and save .res and .clu files from the current sorting object
        save_xml = "{}/{}.xml".format(save_path,SORTING_NAME)
        save_res = "{}/{}.res".format(save_path,SORTING_NAME)
        save_clu = "{}/{}.clu".format(save_path,SORTING_NAME)
        unit_ids = sorting.get_unit_ids()
        if len(unit_ids) > 0:
            spiketrains = [sorting.get_unit_spike_train(u) for u in unit_ids]
            res = np.concatenate(spiketrains).ravel()
            clu = np.concatenate([np.repeat(i+1,len(st)) for i,st in enumerate(spiketrains)]).ravel() # i here counts from 0
            res_sort = np.argsort(res)
            res = res[res_sort]
            clu = clu[res_sort]
        else:
            res = []
            clu = []
        
        unique_ids = np.unique(clu)
        n_clu = len(unique_ids)
            
        clu = np.insert(clu, 0, n_clu) # The +1 is necessary here b/c the convention for the base sorting object is from 1,...,nUnits

        np.savetxt(save_res, res, fmt='%i')
        np.savetxt(save_clu, clu, fmt='%i')
        
        # create parameters file if none exists
        if not os.path.isfile(save_xml):
            soup = BeautifulSoup("",'xml')

            new_tag = soup.new_tag('samplingrate')
            new_tag.string = str(sorting.get_sampling_frequency())
            soup.append(new_tag)

            # write parameters file
            f = open(save_xml, "w")
            f.write(str(soup))
            f.close()


class NeuroscopeMultiSortingExtractor(MultiSortingExtractor):

    """
    Extracts spiking information from an arbitrary number of .res.%i and .clu.%i files in the general folder path.
    
    The .res is a text file with a sorted list of all spiketimes from all units displayed in sample (integer '%i') units.
    The .clu file is a file with one more row than the .res with the first row corresponding to the total number of unique ids in the file (and may exclude 0 & 1 from this count)
    with the rest of the rows indicating which unit id the corresponding entry in the .res file refers to.
    
    In the original Neuroscope format:
        Unit ID 0 is the cluster of unsorted spikes (noise).
        Unit ID 1 is a cluster of multi-unit spikes.
        
    The function defaults to returning multi-unit activity as the first index, and ignoring unsorted noise.
    To return only the fully sorted units, set keep_mua_units=False.
        
    The sorting extractor always returns unit IDs from 1, ..., number of chosen clusters.

    Parameters
    ----------
    folder_path : str
        Optional. Path to the collection of .res and .clu text files. Will auto-detect format.
    keep_mua_units : bool
        Optional. Whether or not to return sorted spikes from multi-unit activity. Defaults to True.
    exclude_inds : list
        Optional. List of indices to ignore. The set of all possible indices is chosen by default, extracted as the final integer of all the .res.%i and .clu.%i pairs.
    """
    extractor_name = 'NeuroscopeMultiSortingExtractor'
    installed = True  # check at class level if installed or not
    is_writable = True
    mode = 'custom'
    installation_mesg = ""  # error message when not installed

    def __init__(self, folder_path, keep_mua_units=True, exclude_shanks=None):
        #SortingExtractor.__init__(self)
            
        _, SORTING_NAME = os.path.split(folder_path)
        xml_filepath = "{}/{}.xml".format(folder_path,SORTING_NAME)
        
        # None of the location arguments were passed
        #assert folder_path is None and resfile_path is None and clufile_path is None, 'Either pass a single folder_path location, or a pair of resfile_path and clufile_path. None received.' # ToDo: examine the logic of this assertion and where it is breaking down
        
        with open(xml_filepath, 'r') as xml_file:
            contents = xml_file.read()
            soup = BeautifulSoup(contents, 'lxml')
            # Normally, this would be a .xml, but there were strange issues
            # in the write_recording method that require it to be a .lxml instead
            # which also requires all capital letters to be removed from the tag names
        
        self._sampling_frequency = float(soup.samplingrate.string) # careful not to confuse it with the lfpsamplingsate
            
        onlyfiles = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]
        
        # Test for detection of single-shank format
        end_res = [x[-3:]=='res' for x in onlyfiles]
        end_clu = [x[-3:]=='clu' for x in onlyfiles]
        any_res = any(end_res)
        any_clu = any(end_clu)
        
        assert any_res != True and any_clu != True, 'Single pair of .res and .clu files identified. Please use the NeuroscopeSortingExtractor to obtain spiking data.'
        
        shank_res_ids = [x[-1] for x in onlyfiles if x[-5:-2] == 'res' and x[-10:-6] != 'temp']
        shank_clu_ids = [x[-1] for x in onlyfiles if x[-5:-2] == 'clu' and x[-10:-6] != 'temp']

        assert shank_res_ids==shank_clu_ids, 'Unmatched .clu.%i and .res.%i files detected!'
        
        all_shanks_list_se = []
        for shank_id in shank_res_ids:
            resfile_path = '{}/{}.res.{}'.format(folder_path,SORTING_NAME,shank_id)
            clufile_path = '{}/{}.clu.{}'.format(folder_path,SORTING_NAME,shank_id)
    
            all_shanks_list_se.append(NeuroscopeSortingExtractor(resfile_path=resfile_path,
                                                                 clufile_path=clufile_path,
                                                                 keep_mua_units=keep_mua_units))
                    

        MultiSortingExtractor.__init__(self,sortings=all_shanks_list_se)
            
        self._kwargs = {'folder_path': str(Path(folder_path).absolute()),
                        'keep_mua_units': keep_mua_units,
                        'exclude_shanks': exclude_shanks}
    
    
    @staticmethod
    def write_sorting(sorting, save_path):
        _, SORTING_NAME = os.path.split(save_path)
            
        # Create and save .res and .clu files from the current sorting object
        save_xml = "{}/{}.xml".format(save_path,SORTING_NAME)
        save_res = "{}/{}.res".format(save_path,SORTING_NAME)
        save_clu = "{}/{}.clu".format(save_path,SORTING_NAME)
        unit_ids = sorting.get_unit_ids()
        if len(unit_ids) > 0:
            spiketrains = [sorting.get_unit_spike_train(u) for u in unit_ids]
            res = np.concatenate(spiketrains).ravel()
            clu = np.concatenate([np.repeat(i+1,len(st)) for i,st in enumerate(spiketrains)]).ravel() # i here counts from 0
            res_sort = np.argsort(res)
            res = res[res_sort]
            clu = clu[res_sort]
        else:
            res = []
            clu = []
        
        unique_ids = np.unique(clu)
        n_clu = len(unique_ids)
            
        clu = np.insert(clu, 0, n_clu) # The +1 is necessary here b/c the convention for the base sorting object is from 1,...,nUnits

        np.savetxt(save_res, res, fmt='%i')
        np.savetxt(save_clu, clu, fmt='%i')
        
        # create parameters file if none exists
        if not os.path.isfile(save_xml):
            soup = BeautifulSoup("",'xml')

            new_tag = soup.new_tag('samplingrate')
            new_tag.string = str(sorting.get_sampling_frequency())
            soup.append(new_tag)

            # write parameters file
            f = open(save_xml, "w")
            f.write(str(soup))
            f.close()