# import matplotlib as matplt
# from pyreg.config_parser import MATPLOTLIB_AGG
# if MATPLOTLIB_AGG:
#     matplt.use('Agg')
import numpy as np
import os
from glob import glob
from functools import reduce
import set_pyreg_paths
import torch
import pyreg.module_parameters as pars
from pyreg.data_utils import make_dir, get_file_name,sitk_read_img_to_std_tensor
import random
import matplotlib.pyplot as plt
import pyreg.simple_interface as SI
import pyreg.fileio as FIO
from torch.autograd import Variable

#######################################################
from pyreg.data_wrapper import AdaptVal

"""
######################################### Section 1. Raw Data Organization  ###############################################

data root:  /playpen/zhenlinx/Data/OAI_segmentation/

The images were saved as nifti format at ./Nifti_6sets_rescaled
The list file are images_6sets_left.txt and images_6sets_right.txt. The images file name are ordered by patient IDs but not ordered by time for each patient.
For a file name like 9000099_20050712_SAG_3D_DESS_LEFT_10424405_image.nii.gz
        9000099 is the patient ID, 20050712 is the scan date,
        SAG_3D_DESS is the image modality, 
        LEFT means left knee, 
        and 10424405 is the image id.

Segmentations for images_6sets_right  predicted by UNetx2 were saved at  
/playpen/zhenlinx/Data/OAI_segmentation/segmentations/images_6sets_right/Cascaded_2_AC_residual-1-s1_end2end_multi-out_UNet_bias_Nifti_rescaled_train1_patch_128_128_32_batch_2_sample_0.01-0.02_cross_entropy_lr_0.0005_scheduler_multiStep_02262018_013038



#######################################  Section 2. Processed Data Organization  #############################################

data root:  /playpen/zyshen/summer/oai_registration/data


The patient id will be saved in patient_id.txt

(to do):The modality list will be saved in modality.txt  ( where each line will be organized as following  MRI  mod1  #newline  CT  mod2 ...........)

the patient slices list will be save in folder  "patient_slice"

./patient_slice/  :                     each patient_id is a separate folder
./patient_slice/idxxxxxxx/:             each modality is a separate folder
./patient_slice/idxxxxxxx/mod1/:        each specificity is a separate folder ie. left,  right
./patient_slice/idxxxxxxx/mod1/spec1/   paths of slice labels will be recorded in "slice_label.txt", each line has a slice path and corresponded label path

########################################   Section 3. Code Organization  ####################################################




class DataPrepare:
                class Dataprepare are specificed to oai_dataset, which will transfer Raw Data Organization into Processed Data Organization
                
                object variable included:
                    raw_data_path, output_data_path, 
                    
                function_call_outside:
                    prepare_data()
                    
                function_call_inside:
                    __factor_file(file_name)
                    __factor_file_list()
                    __build_and_write_in()




class Patient:  
                class Patient are initialized from each patient_id folder, so it need  the path of patient_id folder as input
                
                object varaible included: 
                    basic_information:
                        patient_id, modality (tuple), specificity(tuple), patient_slices_path_dic ([modality][specificity]: slice_list)  (dict),
                        patient_slices_num_dic (dict)
                        
                    annotation_information:
                        has_label, label_is_complete, patient_slices_label_path_dic (dict), 
                
                function called outside:
                    check_if_taken(self, modality=None, specificity=None, len_time_range=None, has_label=None)
                    get_slice_list(modality,specificity)
                    get_label_path_list(modality,specificity)
                    get_slice_num(modality,specificity)
                    
                
                function called inside:
                    __init__()
                    
                    
                    
                
                
                                

class Patients: 
                class Patients are initialized from patient_slice folder, so it need the path of patient_slice folder as input
                this class has a list of Patient class, and can set some condtions in order to filter the patients

                object varaible included:
                    patients_id_list (list), patients( list of class Patient)
                    
                    
                function called outside:
                    get_that_patient(self,patient_id)
                    get_filtered_patients_list(self,modality=None, specificity=None, has_label=None, num_of_patients= -1, len_time_range=None, use_random=False):
                    
                    to do:
                    get_patients_statistic_distribution(is_modality=False, is_specificity= False, has_label=False)
                    
                function call inside:
                     __read_patients_id_list_from_txt(self)
                      __init_basic_info
                      __init_full_info
                      
                      





class OAILongitudeRegistration:
                first, we need to filter some patients  and implement longitude registration,
                
                for each patient, we would registrate images from different time phases to time phase 0
                
                then, we need use the moving map to map label, then do result analysis
                
                functions called outside:
                set_patients()
                set_model()
                do_registration()
                do_result_analysis
                
                
                function called inside:
                __initial_model()
                __inital_source_and_target()
                __do_registration()


                                   

"""

class OAILongitudeReisgtration(object):
    def __init__(self):
        self.patients = []
        self.task_name='oai_reg'
        self.expr_name='debug'
        self.model0_name = 'affine_map'
        self.model1_name = 'svf_vector_momentum_map'
        self.map0_low_res_factor =0.3
        self.map1_low_res_factor =0.3
        self.optimizer0_name = 'sgd'
        self.optimizer1_name = 'lbfgs_ls'
        self.nr_of_iterations = 100
        self.similarity_measure_type='ncc'
        self.similarity_measure_sigma =0.5
        self.visualize_step =10
        self.light_analysis_on=False
        self.par_respro=None
        self.recorder = None
        """if the patient of certain mod and spec has no label, then the light_analysis will automatically on for this patient"""

        self.__initalize_model()




    def set_task_name(self,task_name):
        self.task_name = task_name

    def set_expr_name(self, expr_name):
        self.expr_name = expr_name

    def gen_expr_name(self):
        self.expr_name = self.task_name+ '_'+self.expr_name + '_'+self.model0_name +'_'+self.model1_name+'_mlf_'\
                         +str(self.map0_low_res_factor)+str(self.map1_low_res_factor) + '_op_'+self.optimizer0_name\
                         +self.optimizer1_name+'_sm_'+ self.similarity_measure_type

    def __initalize_model(self):
        self.si = SI.RegisterImagePair()
        self.im_io = FIO.ImageIO()
        self.gen_expr_name()
        if not self.light_analysis_on:
            self.par_respro = self.get_analysis_setting()
            self.par_respro['respro']['expr_name'] = self.expr_name
            self.si.init_analysis_params(self.par_respro,self.task_name)




    def get_analysis_setting(self):
        par_respro = pars.ParameterDict()
        par_respro.load_JSON('../settings/respro_settings.json')
        return par_respro

    def _update_saving_analysis_path(self, path):
        if not self.light_analysis_on:
            self.par_respro['respro']['save_fig_path'] = path

    def __gen_img_saving_path(self,patient, mod, spec):
        current_filename = patient.get_path_for_mod_and_spec(mod, spec)
        folder_path = os.path.join(current_filename, self.expr_name)
        make_dir(folder_path)
        return folder_path



    def set_model(self,model_name):
        self.model_name = model_name


    def set_patients(self, patients):
        if type(patients)!=list:
            patients = [patients]
        self.patients = patients

    def do_registration(self):
        for patient in self.patients:
            self.do_single_patient_registration(patient)


        print("registration for {} patients, finished".format(len(self.patients)))

        if not self.light_analysis_on:
            self.recorder = self.si.get_recorder()
            self.recorder.set_summary_based_env()
            self.recorder.saving_results(sched='summary')


    def do_single_patient_registration(self,patient):
        print('start processing patient {}'.format(patient.patient_id))
        for mod in patient.modality:
            for spec in patient.specificity:
                if patient.get_slice_num(mod,spec)>0:
                    print('---- start processing mod {}, spec {}'.format(mod, spec))

                    self.si.set_light_analysis_on(self.light_analysis_on)
                    self.do_single_patient_mod_spec_registration(patient,mod,spec)




    def do_single_patient_mod_spec_registration(self,patient,mod,spec):
        patient_id = patient.patient_id
        img_paths = patient.get_slice_list(mod,spec)
        img0_path = img_paths[0]
        img0_name = get_file_name(img0_path)
        extra_info ={}
        Ic0, hdrc0, spacing0,_ = self.im_io.read_to_nc_format(filename=img0_path, intensity_normalize=True)
        print(Ic0.shape)
        LSource = None
        LTarget = None
        if not self.light_analysis_on:
            label_path = None if not patient.patient_has_label_dic[mod][spec] else patient.get_label_path_list()
            if label_path:
                try:
                    LTarget= AdaptVal(Variable(sitk_read_img_to_std_tensor(label_path[0])))
                except:
                    LTarget, _, _, _ = self.im_io.read_to_nc_format(filename=label_path[0], intensity_normalize=False)
            else:
                print("complete analysis will be skipped for patient_id {}, modality{}, specificity{}".format(patient_id,mod, spec))
                self.si.set_light_analysis_on(True)
                return None



        saving_folder_path = self.__gen_img_saving_path(patient,mod, spec)
        self._update_saving_analysis_path(saving_folder_path)

        self.im_io.write(os.path.join(saving_folder_path, img0_name+'.nii.gz'), np.squeeze(Ic0), hdrc0)
        for i,img_path in enumerate(img_paths[1:]):
            img1_name = get_file_name(img_path)
            extra_info['pair_name']=[img1_name+'_'+img0_name +'_step1']
            extra_info['batch_id']=img1_name+'_'+img0_name +'_step1'


            Ic1, hdrc, spacing, _ = self.im_io.read_to_nc_format(filename=img_path, intensity_normalize=True)

            if LTarget is not None:
                if label_path:
                    try:
                        LSource = AdaptVal(Variable(sitk_read_img_to_std_tensor(label_path[i])))
                    except:
                        LSource, _, _, _ = self.im_io.read_to_nc_format(filename=label_path[i], intensity_normalize=False)
                else:
                    assert("source label not find")

            # if self.recorder is not None:
            #     self.si.set_recorder(self.recorder)
            self.si.set_light_analysis_on(True)
            self.si.register_images(Ic1, Ic0, spacing,extra_info=extra_info,LSource=LSource,LTarget=LTarget,
                                    model_name=self.model0_name,
                                    map_low_res_factor=self.map0_low_res_factor,
                                    nr_of_iterations=self.nr_of_iterations,
                                    visualize_step=None,
                                    optimizer_name=self.optimizer0_name,
                                    use_multi_scale=True,
                                    rel_ftol=1e-9,
                                    similarity_measure_type=self.similarity_measure_type,
                                    similarity_measure_sigma=self.similarity_measure_sigma,
                                    json_config_out_filename='cur_settings.json',
                                    params ='cur_settings.json')
            wi = self.si.get_warped_image()
            wi=wi.cpu().data.numpy()

            # if not self.light_analysis_on:
            #     self.recorder = self.si.get_recorder()

            print("let's come to step 2 ")
            self.si.set_light_analysis_on(self.light_analysis_on)
            extra_info['pair_name'] = [img1_name + '_' + img0_name + '_step2']
            extra_info['batch_id'] = img1_name + '_' + img0_name + '_step2'
            self.si.register_images(wi, Ic0, spacing,extra_info=extra_info,LSource=LSource,LTarget=LTarget,
                                    model_name=self.model1_name,
                                    map_low_res_factor=self.map1_low_res_factor,
                                    nr_of_iterations=self.nr_of_iterations,
                                    visualize_step=self.visualize_step,
                                    optimizer_name=self.optimizer1_name,
                                    use_multi_scale=True,
                                    rel_ftol=1e-9,
                                    similarity_measure_type= self.similarity_measure_type,
                                    similarity_measure_sigma=self.similarity_measure_sigma,
                                    json_config_out_filename='output_settings_lbfgs.json',
                                    params='cur_settings_lbfgs.json')

            wi = self.si.get_warped_image()
            img_name = os.path.split(img_path)[1]
            self.im_io.write(os.path.join(saving_folder_path,img_name+'.nii.gz'), torch.squeeze(wi), hdrc)





class Patients(object):
    def __init__(self,full_init=False):
        self.full_init = full_init
        self.root_path = "/playpen/zyshen/summer/oai_registration/data"
        self.patients_id_txt_name = 'patient_id.txt'
        self.patients_info_folder = 'patient_slice'
        self.patients_id_list= []
        self.patients = []
        if not full_init:
            self.__init_basic_info()
        else:
            self.__init_full_info()


    def __init_basic_info(self):
        self.__read_patients_id_list_from_txt()
        self.patients_num = len(self.patients_id_list)


    def __init_full_info(self):
        self.__read_patients_id_list_from_txt()
        self.patients_num = len(self.patients_id_list)
        for patient_id in self.patients_id_list:
            patient_info_path = os.path.join(self.root_path, self.patients_info_folder, patient_id)
            self.patients.append(Patient(patient_info_path))

    def get_all_patients(self):
        if self.full_init:
            return self.patients
        else:
            self.__init_full_info()
            return self.patients

    def get_that_patient(self,patient_id):
        assert patient_id in self.patients_id_list
        patient_info_path = os.path.join(self.root_path, self.patients_info_folder, patient_id)
        patient = Patient(patient_info_path)
        return patient



    def get_filtered_patients_list(self,modality=None, specificity=None, has_label=None, num_of_patients= -1, len_time_range=None, use_random=False):
        index = list(range(self.patients_num))
        num_of_patients = num_of_patients if num_of_patients>0 else self.patients_num
        filtered_patients_list =[]
        if use_random:
            random.shuffle(index)
        count = 0
        for i in index:
            if not self.full_init:
                patient_id = self.patients_id_list[i]
                patient_info_path = os.path.join(self.root_path, self.patients_info_folder, patient_id)
                patient = Patient(patient_info_path)
            else:
                patient = self.patients[i]
            modality = patient.modality[0] if modality is None else modality
            specificity = patient.specificity[0] if specificity is None else specificity
            if_taken = patient.check_if_taken(modality=modality,specificity=specificity,has_label=has_label,len_time_range=len_time_range)
            if if_taken:
                filtered_patients_list.append(patient)
                count+=1
                if count>= num_of_patients:
                    break
        if len(filtered_patients_list)< num_of_patients:
            print("not enough patients meet the filter requirement. We want {} but got {} patients".format(num_of_patients, len(filtered_patients_list)))
        return filtered_patients_list





    def __read_patients_id_list_from_txt(self):
        """
        get the patient id from the txt i.e patient_id.txt
        :param file_name:
        :return: type list, list of patient id
        """

        txt_path = os.path.join(self.root_path, self.patients_id_txt_name)
        with open(txt_path, 'r') as f:
            content = f.read().splitlines()
            if len(content) > 0:
                infos = [line.split('\t') for line in content]
            self.patients_id_list = [info[0] for info in infos]
            self.patients_has_label_list = [info[1]=='annotation_complete' for info in infos]




class Patient():
    def __init__(self, path):
        # patient_id, modality(set), specificity(set), patient_slices_path_dic([modality][specificity]: slice_list)
        self.patient_root_path = path
        self.patient_id = -1
        self.modality = None
        self.specificity = None
        self.patient_slices_path_dic = {}
        self.patient_slices_num_dic = {}
        self.has_label = False
        self.label_is_complete = True
        self.patient_slices_label_path_dic = {}
        self.patient_has_label_dic= {}
        self.txt_file_name = 'slice_label.txt'
        self.__init_patient_info()


    def __init_patient_info(self):
        self.patient_id = os.path.split(self.patient_root_path)[1]
        modality_list = os.listdir(self.patient_root_path)
        specificity_list = os.listdir(os.path.join(self.patient_root_path, modality_list[0]))
        self.modality = tuple(modality_list)
        self.specificity = tuple(specificity_list)
        for mod in self.modality:
            for spec in self.specificity:
                if mod not in self.patient_slices_path_dic:
                    self.patient_slices_path_dic[mod]={}
                    self.patient_slices_label_path_dic[mod]={}
                    self.patient_has_label_dic[mod]= {}
                    self.patient_slices_num_dic[mod]={}
                self.patient_slices_path_dic[mod][spec], self.patient_slices_label_path_dic[mod][spec] \
                    = self.__init_path_info(mod, spec)
                self.patient_slices_num_dic[mod][spec] = len(self.patient_slices_path_dic[mod][spec])
                has_complete_spec_label = True
                for label_path in self.patient_slices_label_path_dic[mod][spec]:
                    if label_path !='None':
                        self.has_label = True
                    else:
                        self.label_is_complete= False
                        has_complete_spec_label= False
                self.patient_has_label_dic[mod][spec] = has_complete_spec_label



    def __init_path_info(self,modality, specificity):
        txt_path = os.path.join(self.patient_root_path,modality, specificity,self.txt_file_name)
        paths = []
        with open(txt_path, 'r') as f:
            content = f.read().splitlines()
            if len(content) > 0:
                paths = [line.split('\t') for line in content]
            slices_path_list = [path[0] for path in paths]
            slices_label_path_list = [path[1] for path in paths]
        return slices_path_list,slices_label_path_list

    def check_if_taken(self, modality=None, specificity=None, len_time_range=None, has_label=None):
        modality_met =True if modality is None else modality in self.modality
        specificity_met = True if specificity is None else  specificity in self.specificity
        has_label_met = True if has_label is None else self.label_is_complete == has_label
        if modality not in self.modality or specificity not in self.specificity:
            return False

        len_time_met =True
        if len_time_range is not None:
            cur_len_time = self.patient_slices_num_dic[modality][specificity]
            len_time_met = len_time_range[0]<= cur_len_time and len_time_range[1]>= cur_len_time
        if_taken = modality_met and specificity_met and len_time_met and has_label_met
        return if_taken

    def get_slice_list(self, modality=None, specificity=None):
        if modality==None and specificity==None:
            return self.patient_slices_path_dic[self.modality[0]][self.specificity[0]]
        elif modality in self.modality and specificity in self.specificity:
            return self.patient_slices_path_dic[modality][specificity]
        else:
            print("patient{} doesn't has slice in format {} and {}".format(self.patient_id, modality, specificity))
            return []


    def get_label_path_list(self,modality=None, specificity=None):
        if modality==None and specificity==None:
            return self.patient_slices_label_path_dic[self.modality[0]][self.specificity[0]]
        elif modality in self.modality and specificity in self.specificity:
            return self.patient_slices_label_path_dic[modality][specificity]
        else:
            print ("patient{} doesn't has label in format {} and {}".format(self.patient_id, modality, specificity))
            return []

    def get_slice_num(self,modality=None, specificity=None):
        if modality==None and specificity==None:
            return self.patient_slices_num_dic[self.modality[0]][self.specificity[0]]
        elif modality in self.modality and specificity in self.specificity:
            return self.patient_slices_num_dic[modality][specificity]
        else:
            print("patient{} doesn't has slice in format {} and {}".format(self.patient_id, modality, specificity))
            return 0

    def get_path_for_mod_and_spec(self,mod,spec):
        if self.get_slice_num(mod,spec)>0:
            path = os.path.join(self.patient_root_path,mod,spec)
            return path
        else:
            return None






class OAIDataPrepare():
    def __init__(self):
        self.raw_data_path = "/playpen/zhenlinx/Data/OAI_segmentation/Nifti_6sets_rescaled"
        self.raw_label_path = "/playpen/zhenlinx/Data/OAI_segmentation/segmentations/images_6sets_right/Cascaded_2_AC_residual-1-s1_end2end_multi-out_UNet_bias_Nifti_rescaled_train1_patch_128_128_32_batch_2_sample_0.01-0.02_cross_entropy_lr_0.0005_scheduler_multiStep_02262018_013038"
        self.output_root_path = "/playpen/zyshen/summer/oai_registration/data"
        self.output_data_path = "/playpen/zyshen/summer/oai_registration/data/patient_slice"
        self.raw_file_path_list = []
        self.raw_file_label_path_list= []
        self.patient_info_dic= {}
        self.file_end = '*.nii.gz'

    def prepare_data(self):
        self.get_file_list()
        self.__factor_file_list()
        self.__build_and_write_in()


    def __filter_file(self, path, file_end):
        f_filter =[]
        import fnmatch
        for root, dirnames, filenames in os.walk(path):
            for filename in fnmatch.filter(filenames, file_end):
                f_filter.append(os.path.join(root, filename))
        return f_filter


    def get_file_list(self):

        self.raw_file_path_list = self.__filter_file(self.raw_data_path,self.file_end)
        self.raw_file_label_path_list = self.__filter_file(self.raw_label_path,self.file_end)


    def __factor_file(self, f_path):
        """
        For a file name like 9000099_20050712_SAG_3D_DESS_LEFT_10424405_image.nii.gz
        9000099 is the patient ID, 20050712 is the scan date,
        SAG_3D_DESS is the image modality,
        LEFT means left knee,
        and 10424405 is the image id.
        :return:
        """
        file_name = os.path.split(f_path)[-1]
        factor_list = file_name.split('_')
        patient_id = factor_list[0]
        scan_date = int(factor_list[1])
        modality = factor_list[2] + '_' + factor_list[3] + '_'+factor_list[4]
        specificity = factor_list[5]
        f = lambda x,y : x+'_'+y
        file_name = reduce(f,factor_list[:7])
        return {'file_path': f_path,'slice_name': file_name,'patient_id':patient_id, 'scan_date':scan_date, 'modality':modality, 'specificity':specificity,'label_path':'None'}



    def __factor_file_list(self):

        for f_path in self.raw_file_path_list:
            fd = self.__factor_file(f_path)
            if fd['patient_id'] not in self.patient_info_dic:
                self.patient_info_dic[fd['patient_id']] = {}
            if fd['modality'] not in self.patient_info_dic[fd['patient_id']]:
                self.patient_info_dic[fd['patient_id']][fd['modality']] = {}
            if fd['specificity'] not in self.patient_info_dic[fd['patient_id']][fd['modality']]:
                self.patient_info_dic[fd['patient_id']][fd['modality']][fd['specificity']] = {}
            cur_dict = self.patient_info_dic[fd['patient_id']][fd['modality']][fd['specificity']][fd['slice_name']]={}
            cur_dict['file_path'] =fd['file_path']
            cur_dict['slice_name'] =fd['slice_name']
            cur_dict['scan_date'] =fd['scan_date']
            cur_dict['label_path'] = fd['label_path']



        for f_path in self.raw_file_label_path_list:
            fd = self.__factor_file(f_path)
            self.patient_info_dic[fd['patient_id']][fd['modality']][fd['specificity']][fd['slice_name']]['label_path'] = f_path




    def __build_and_write_in(self):
        with open(os.path.join(self.output_root_path,'patient_id.txt'),'w') as fr:
            has_label = True
            for pat_id in self.patient_info_dic:
                for mod in self.patient_info_dic[pat_id]:
                    for spec in self.patient_info_dic[pat_id][mod]:
                        folder_path = os.path.join(self.output_data_path,pat_id,mod,spec)
                        make_dir(folder_path)
                        slices_info_dict = self.patient_info_dic[pat_id][mod][spec]
                        sorted_slice_name_list = self.__sort_by_scan_date(slices_info_dict)
                        with open(os.path.join(folder_path,'slice_label.txt'), 'w') as f:
                            for name in sorted_slice_name_list:
                                f.write(slices_info_dict[name]['file_path'])
                                f.write("\t")
                                f.write(slices_info_dict[name]['label_path'])
                                f.write("\n")
                                has_label = has_label if slices_info_dict[name]['label_path'] !='None' else False
                label_complete_str = 'annotation_complete' if has_label else 'annotation_not_complete'
                fr.write(pat_id +'\t' + label_complete_str +'\n')





    def __sort_by_scan_date(self, info_dict):
        slices_name_list=[]
        slices_date_list= []
        for slice in info_dict:
            slices_name_list.append(info_dict[slice]['slice_name'])
            slices_date_list.append(info_dict[slice]['scan_date'])
        slices_name_np = np.array(slices_name_list)
        slices_date_np = np.array(slices_date_list)
        sorted_index = np.argsort(slices_date_np)
        slices_name_np = slices_name_np[sorted_index]
        return list(slices_name_np)




# test = OAIDataPrepare()
# test.prepare_data()
patients = Patients()
filtered_patients = patients.get_filtered_patients_list(specificity='RIGHT',num_of_patients=1, len_time_range=[2,7], use_random=False)
oai_reg = OAILongitudeReisgtration()
oai_reg.set_patients(filtered_patients)
oai_reg.do_registration()