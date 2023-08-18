import os
import json
import synapseclient
import pandas as pd
import numpy as np

syn = synapseclient.Synapse()
syn.login(authToken=os.environ.get('SYNAPSE_PAT'))

# read in metadata templates and convert to ... data frame?

# list files in directory

# a function to get file paths from all subdirs in directory
def getFullPaths(directory):
    full_paths = list()
    for root, dirs, files in os.walk(os.path.abspath(path)):
        for file in files:
            full_paths.append(os.path.join(root, file))
    return full_paths

# get file paths for all template schemas
path = 'schema_metadata_templates/'
file_paths = getFullPaths(path)

# append None type to required column if no columns are required in the template schema
def append_required(required_list, json_stuff):
    if 'required' in json_stuff:
        required_list.append(json_stuff['required'])
    else: 
        required_list.append(None)    


# create data frame of attributes representing metadata templates, i.e. Parent = "DataType"
def createTemplateDataFrame(file_path_list):

    # actually do do lists
    attribute = list()
    schema_id = list()
    description = list()
    dependsOn = list()
    csv_properties = list() # properties column in csv, not properties defined in json schema
    schema_required_columns = list() # store as an additional column for later
    template_required = list()
    valid_values = list()
    parent = list()
    dependsOn_component = list()
    validation_rules = list()

    # loop over the file paths of the metadata template json schemas
    for file_name in file_path_list:
        # open the file and read the json
        file = open(file_name)
        json_schema = json.load(file)
        # populate lists with values from each template schema
        attribute_name = os.path.basename(file_name).replace('.json', '')
        attribute.append(attribute_name)
        schema_id.append(json_schema['$id'])
        description.append(json_schema['description'])
        dependsOn.append(', '.join(json_schema['properties']))
        csv_properties.append(None)
        append_required(schema_required_columns, json_schema)
        template_required.append('FALSE')
        valid_values.append(None)
        parent.append('DataType')
        dependsOn_component.append(None)
        validation_rules.append(None)

    # make the data frame
    df = pd.DataFrame({'Attribute': attribute,
                       'Description': description, 
                       'Valid Values': valid_values,
                       'DependsOn': dependsOn,
                       'Properties': csv_properties,
                       'Required': template_required,
                       'Parent': parent,
                       'DependsOn Component': dependsOn_component,
                       'Source': schema_id,
                       'Validation Rules': validation_rules,
                       'Schema Required Columns': schema_required_columns} 
                       )
    
    return(df)

template_df = createTemplateDataFrame(file_paths)

# get column "mini-schemas" and valid values in table form from synapse annotations project
annotation_modules_id = 'syn10242922'
schema_versions_id = 'syn26050066'

query_results = syn.tableQuery("select * from %s" % schema_versions_id)
schema_versions = query_results.asDataFrame()

query_results = syn.tableQuery("select * from %s" % annotation_modules_id)
annotation_modules = query_results.asDataFrame()

# remove the PEC specific modules from the annotations table to prevent problems w/ grant and study
annotation_modules = annotation_modules.loc[annotation_modules['module'] != 'PsychENCODESpecific']

# what are the column attributes from all templates?
dep_column_values = template_df['DependsOn'].tolist()
dep_list = list()
for i in dep_column_values:
    ls = str.split(i.replace(',', ''))
    dep_list = dep_list + ls
dep_array = np.array(dep_list)
unique_deps = np.unique(dep_array).tolist()

# get rows from the schema versions table that match our attribute dependencies
schema_versions.loc[schema_versions['key'].isin(unique_deps)]

# duplicates for study and grant -- probably from PEC
schema_versions.loc[schema_versions['key'].isin(unique_deps)].groupby('key').size().sort_values(ascending = False)
schema_versions.loc[schema_versions['key'] == 'study'] # yep

# get all unique keys from AD
all_ad_keys = schema_versions.loc[(schema_versions['key'].isin(unique_deps)) 
                    & (schema_versions['module'] != 'PsychENCODESpecific')][['key', 'schema', 'latestVersion']]

# join key descriptions from the annotation table
key_definitions = annotation_modules[['key', 'description', 'columnType']].drop_duplicates()
# this is the row info for column attributes, aka Parent = "DataProperty"
merged_keys_defs = pd.merge(all_ad_keys, 
                  key_definitions,
                  how = 'left',
                  on = ['key'])

# get list of all unique required keys
req_column_values = template_df.loc[template_df['Schema Required Columns'].notna()]['Schema Required Columns'].tolist()
req_list = list()
for i in req_column_values:
    req_list = req_list + i
req_array = np.array(req_list)
unique_reqs = np.unique(req_array).tolist()

# combine schema id and version into source column
merged_keys_defs['Source'] = merged_keys_defs[['schema', 'latestVersion']].agg('-'.join, axis=1)

# get column of valid values for attributes
def getValidValues(attribute):
    if any(annotation_modules['key'].str.contains(attribute)):
        sub_df = annotation_modules.loc[annotation_modules['key'] == attribute]
        if sub_df['value'].isna().all():
            value_string = ''
        else:
            value_list = sub_df['value'].tolist()
            value_string = ', '.join(value_list)
    else:
        value_string = ''
    return(value_string)


valid_values = list()
for item in merged_keys_defs['key']:
    valid_values.append(getValidValues(item)) 


# create data frame of attributes representing template columns, i.e. Parent = 'DataProperty'
# lists that will be columns
attribute = list(merged_keys_defs['key'])
schema_id = list(merged_keys_defs['Source'])
description = list(merged_keys_defs['description'])
dependsOn = list()
csv_properties = list() # properties column in csv, not properties defined in json schema
schema_required_columns = list() # store as an additional column for later
attribute_required = list()
valid_values = list()
parent = list()
dependsOn_component = list()
validation_rules = list()
needs_boolean_fix = list() # store for later -- boolean is not an available schematic type and T/F values don't have namespaces


for a in attribute:
    dependsOn.append(None)
    csv_properties.append(None)
    if a in unique_reqs:
        attribute_required.append('TRUE')
    else:
        attribute_required.append('FALSE')
    valid_values.append(getValidValues(a))
    parent.append('DataProperty')
    dependsOn_component.append(None)
    if merged_keys_defs.loc[merged_keys_defs['key'] == a]['columnType'].values[0] != 'boolean':
        validation_rules.append(merged_keys_defs.loc[merged_keys_defs['key'] == a]['columnType'].values[0][0:3])
        needs_boolean_fix.append(None)
    else:
        validation_rules.append(None)
        needs_boolean_fix.append('YES')

df = pd.DataFrame({'Attribute': attribute,
                       'Description': description, 
                       'Valid Values': valid_values,
                       'DependsOn': dependsOn,
                       'Properties': csv_properties,
                       'Required': attribute_required,
                       'Parent': parent,
                       'DependsOn Component': dependsOn_component,
                       'Source': schema_id,
                       'Validation Rules': validation_rules,
                       'Adjust Bool': needs_boolean_fix} 
                       )



basic_model = pd.concat([template_df, df], ignore_index = True)
