#!/usr/bin/env python

# Created 2016-09-25, Jordi Huguet, Dept. Radiology AMC Amsterdam

####################################
__author__      = 'Jordi Huguet'  ##
__dateCreated__ = '20160925'      ##
__version__     = '0.1.0'         ##
__versionDate__ = '20160927'      ##
####################################

# qap_output_ingestor.py
# load csv file, parse out all QAP values found, compose XNAT-compliant XML blobs and upload them to XNAT instance 


# IMPORT FUNCTIONS
import os
import sys
import csv
import urllib
import traceback
from lxml import etree
from datetime import datetime
import xnatLibrary


# GLOBAL NAMESPACES 
ns_xnat = { 'xnat' : 'http://nrg.wustl.edu/xnat' }
    
    
# FUNCTIONS
def normalize_string(data):
    '''Helper function for replacing awkward chars for underscores'''
    '''Returns a normalized string valid as XNAT identifier/label/name'''
    
    data = data.replace("/", " ")
    data = data.replace(",", " ")
    data = data.replace(".", " ")
    data = data.replace("^", " ")
    data = data.replace(" ", "_")
    
    return data
    
    
def get_scan_type_xnat(xnat_connection,projectID,subjectName,experimentName,scanID):
    ''' Helper function to get the type of an existing scan resource in an XNAT imaging session '''
    ''' Returns a scan type definition '''    
    
    #compose the URL for the REST call
    URL = xnat_connection.host + '/data/projects/%s/subjects/%s/experiments/%s/scans' %(projectID,subjectName,experimentName)
    
    #encode query options
    query_options = {}
    query_options['format'] = 'json'
    query_options = urllib.urlencode(query_options)
            
    #do the HTTP query
    response_data,response = xnat_connection.queryURL(URL,query_options)    
    
    scan_type = [item['type'] for item in response_data if item['ID'] == scanID]
    assert len(scan_type) == 1
    
    return str(scan_type[0])
    

def upload_to_XNAT(xnat_connection,project,subject,session,assessor,xml_data,dateType_ID):                            
    '''Uploads an XML object representing an image-related assessment dataType instance'''
    '''Returns the unique ID of the created assessment'''
        
    #compose the URL for the REST call
    URL = xnat_connection.host + '/data/projects/'
    URL += project
    URL += '/subjects/'
    URL += subject
    URL += '/experiments/'
    URL += session
    URL += '/assessors/'
    URL += assessor
     
    if xnat_connection.resourceExist(URL).status == 200 :
        raise xnatLibrary.XNATException('Assessment with same name %s already exists' %assessor )
    else:                            
        #encode query options
        opts_dict = {}
        #opts_dict['xsiType'] = '%s' %dateType_ID
        opts_dict['inbody'] = 'true'
        opts = urllib.urlencode(opts_dict)
        
        #Convert the options to an encoded string suitable for the HTTP request
        print URL 
        print xml_data
        print opts
        resp,experiment_uid = xnat_connection.putData(URL, xml_data, opts)
        
        if resp.status == 201 : 
            print '[info] Assessment %s (UID: %s) of type %s successfully created' %(assessor,experiment_uid,dateType_ID)
            
    return experiment_uid
    
    
def create_xml_header(namespace, main_object_id):
    ''' Helper for composing the header of an XML element containing the XNAT output data '''
    ''' Returns an etree structure (lxml module)'''
    
    # Start printing the XML document.
    xmlHeader_preamble = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xmlHeader_preamble += '<!-- XNAT XML generated by %s - %s on %s -->' %(os.path.basename(sys.argv[0]),__author__,str(datetime.now().replace(microsecond=0)))
    xmlHeader_start = ( '<'+namespace+ ':' + main_object_id+' '
                        'xmlns:'+namespace+'="http://nrg.wustl.edu/'+namespace+'" ' 
                        'xmlns:xnat="http://nrg.wustl.edu/xnat" ' 
                        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' )
                        #'xsi:schemaLocation= ...">' )
    xmlHeader_end = '</'+namespace+ ':' + main_object_id+'>'
    
    xml_header = xmlHeader_preamble + '\n' + xmlHeader_start + '\n' + xmlHeader_end
    root_xml_element = etree.fromstring(xml_header)
    
    return root_xml_element

    
def add_xml_subElement(root_elem, namespace_uri, elem_name, elem_value):
    ''' Helper for creating XML object sub-elements and populating them '''
    ''' Returns an etree subelement (lxml module)'''   
    
    elem = etree.SubElement(root_elem, "{%s}%s" %(namespace_uri,elem_name))
    elem.text = str(elem_value)
    
    return elem
    

def add_xml_attributes(elem, attributes):
    ''' Helper for creating XML object sub-elements and populating them '''
    ''' Returns an etree subelement (lxml module)'''   
    
    for attribute_key in attributes.keys() :
        elem.attrib[attribute_key]=attributes[attribute_key]
    
    return elem
    

def populate_data(xml_root_elem, data,namespace, root_measures_list, nested_measures_dict):
    ''' Function for filling-in computed QAP measurements into existing XML object '''
    ''' Returns an XML root element fully populated with data elements '''
    
    # Add computed QAP measurements to XML object
    for measure in data.keys():
        # if a root XML element measure, just add the subelement
        if measure in root_measures_list :
            add_xml_subElement(xml_root_elem, namespace.values()[0], measure, data[measure])
        # if a nested measure, create the subelement if needed and add measure as an XML attribute 
        elif measure in nested_measures_dict.keys() :
            # check if subelement exists before adding attribute (usecase fwhm)
            elem_xpath = './/' + namespace.keys()[0] + ':' + nested_measures_dict[measure]
            elem = xml_root_elem.find(elem_xpath, namespace)
            if elem is None :
                # otherwise create it
                elem = add_xml_subElement(xml_root_elem, namespace.values()[0], nested_measures_dict[measure], '' )
            # update subelement attributes
            add_xml_attributes(elem, { measure : data[measure] } )
    
    return xml_root_elem
    
    
def populate_xml_obj(xml_root_elem, data, namespace, xml_element_type, scan_id, scan_type):
    ''' Function for inserting computed QAP measurements into an (XNAT schema-compliant) XML object '''
    ''' Returns an XML root element populated with all data '''
    
    # static definitions for fMRI SPATIAL QAP metrics
    fspat_root_measures_list = ['efc', 'snr', 'fber', 'fwhm']
    fspat_nested_measures_dict = { 'ghost_x' : 'gsr', 'ghost_y' : 'gsr', 'ghost_z' : 'gsr',
                                   'fg_mean' : 'fg', 'fg_size' : 'fg', 'fg_std' : 'fg',
                                   'bg_mean' : 'bg', 'bg_size' : 'bg', 'bg_std' : 'bg',
                                   'fwhm_x' : 'fwhm', 'fwhm_y' : 'fwhm', 'fwhm_z' : 'fwhm'
                                 }
    
    # static definitions for fMRI TEMPORAL QAP metrics
    ftemp_root_measures_list = ['quality', 'm_tsnr', 'fber', 'outlier', 'dvars', 'gcor']
    ftemp_nested_measures_dict = { 'mean_fd' : 'fd', 'num_fd' : 'fd', 'perc_fd' : 'fd' }
    
    # static definitions for structural MRI QAP metrics
    anat_root_measures_list = ['cnr', 'efc', 'snr', 'fber', 'qi1', 'gcor']     
    anat_nested_measures_dict = {  'gm_mean' : 'gm', 'gm_size' : 'gm', 'gm_std' : 'gm',
                                   'wm_mean' : 'wm', 'wm_size' : 'wm', 'wm_std' : 'wm',
                                   'csf_mean' : 'csf', 'csf_size' : 'csf', 'csf_std' : 'csf',
                                   'fg_mean' : 'fg', 'fg_size' : 'fg', 'fg_std' : 'fg',
                                   'bg_mean' : 'bg', 'bg_size' : 'bg', 'bg_std' : 'bg',
                                   'fwhm_x' : 'fwhm', 'fwhm_y' : 'fwhm', 'fwhm_z' : 'fwhm'
                                 }
    
    add_xml_subElement(xml_root_elem, ns_xnat['xnat'], 'date', datetime.now().date())
    add_xml_subElement(xml_root_elem, ns_xnat['xnat'], 'time', datetime.now().replace(microsecond=0).time())
    
    scan_elem = add_xml_subElement(xml_root_elem, namespace.values()[0], 'scan', '' )
    add_xml_attributes(scan_elem, { 'ID' : scan_id, 'type' : scan_type } )
    
    if xml_element_type == 'AMCZ0:fspatQA' :
        xml_root_elem = populate_data(xml_root_elem,data,namespace, fspat_root_measures_list, fspat_nested_measures_dict)
    elif xml_element_type == 'AMCZ0:ftempQA' :        
        xml_root_elem = populate_data(xml_root_elem,data,namespace, ftemp_root_measures_list, ftemp_nested_measures_dict)
    elif xml_element_type == 'AMCZ0:anatQA' :        
        xml_root_elem = populate_data(xml_root_elem,data,namespace, anat_root_measures_list, anat_nested_measures_dict)
        
    return xml_root_elem
    

def create_xml_obj(data,xml_element_type, scan_id, scan_type):
    ''' main function for the creation of the XNAT-compliant XML object '''
    ''' Returns an XML root element populated with all QAP processing data '''
    
    namespace,dataType_ID = xml_element_type.split(':')
    current_ns = { namespace : 'http://nrg.wustl.edu/'+namespace }
        
    # create & populate data into newly-created XML object (XNAT dataType schema compliant)
    xml_elem = create_xml_header(namespace,dataType_ID)
    xml_elem = populate_xml_obj(xml_elem, data, current_ns, xml_element_type, scan_id, scan_type)
    
    return xml_elem
    

def fix_results_type(parsed_results_list) :
    ''' Turns out that QAP returns some resulting integer values as decimal values, lets re-cast them '''
    ''' Fix the types, otherwise XML scheming machinery will laudly complain about invalid XML subelements '''
    
    integer_typed_results = [ 'num_fd', 'fg_size', 'bg_size', 'gm_size', 'wm_size', 'csf_size' ]
    
    for parsed_results_dict in parsed_results_list :
        for result_element in integer_typed_results : 
            if parsed_results_dict.get(result_element):
               parsed_results_dict[result_element] = str(int(float(parsed_results_dict[result_element])))
    
    return parsed_results_list
    
def parse_csv_file(csv_filepath):
    ''' Parse out a CSV-formatted file to a python structure (list of dictionaries) '''
    ''' Each row entry will be coded as a dictionery (key = header) and all appended in a returned list '''
    
    rows_dict_list = []

    with open(csv_filepath, mode='r') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            rows_dict_list.append(dict(row))

    return rows_dict_list

    
def main (argument_list):
    
    header_msg = '%s - v%s' %(os.path.basename(argument_list[0]),__version__)
    
    if len(argument_list) != 7 :
        print '[error] No valid arguments supplied (%s)' %header_msg
        sys.exit(1)
    
    # input argument list
    usr_pwd = argument_list[1]
    hostname = argument_list[2]
    project = argument_list[3]
    csv_input_file = argument_list[4]
    qap_analysis_type = argument_list[5] # either {temporal, spatial}
    scan_type = argument_list[6] # either {anat, func}
    
    # check the main XML element type (XNAT datatype)
    if 'anat' in scan_type.lower():
        xml_element_type = 'AMCZ0:anatQA'
    elif 'func' in scan_type.lower():
        if qap_analysis_type.lower() == 'spatial' :
            xml_element_type = 'AMCZ0:fspatQA'
        elif qap_analysis_type.lower() == 'temporal' :
            xml_element_type = 'AMCZ0:ftempQA'
    
    if xml_element_type not in ['AMCZ0:anatQA','AMCZ0:fspatQA','AMCZ0:ftempQA'] :
        print '[error] No valid QAP or scan type recognized (%s)' %header_msg
        sys.exit(1)
    
    # parse out data from CSV file containing results generated by QAP run 
    parsed_results = parse_csv_file(csv_input_file)
    parsed_results = fix_results_type(parsed_results)
    
    # connect to XNAT
    try:
        with xnatLibrary.XNAT(hostname,usr_pwd) as xnat_connection :
        
            # for each entry (row) in the results file, create an XML object instantiating an XNAT assessment/experiment
            for scan_results in parsed_results:
                
                scan_id = scan_results['scan'].split('_')[1]
                scan_type = xnat_scan_type = get_scan_type_xnat(xnat_connection,project,scan_results['subject'],scan_results['session'],scan_id)
                xml_element = create_xml_obj(scan_results,xml_element_type, scan_id, scan_type)    
                
                # Do some magic :: upload xml object into XNAT (instantiate a new dataType object)
                assessment_label = normalize_string( scan_results['subject'] + '_' + scan_results['session'] + '_s' + scan_results['scan'].split('_')[1] + '_' + xml_element_type.split(':')[1] )
                
                upload_to_XNAT(xnat_connection,project,scan_results['subject'],scan_results['session'],assessment_label,etree.tostring(xml_element),xml_element_type)        
    
    except xnatLibrary.XNATException as xnatErr:
        print '[error] XNAT-related issue(%s): %s' %(header_msg,xnatErr)
        sys.exit(1)
    
    except Exception as e:
        print '[error]', e	
        print(traceback.format_exc())
        sys.exit(1)
    
# TOP-LEVEL SCRIPT ENVIRONMENT
if __name__=="__main__" :
    
    main(sys.argv) 
    sys.exit(0)
