"""
This Python script cleans and processes the ECan/Ashley Future Coasts GWL timeseries data
created Evelyn_Charlesworth
finalised BY person: Patrick Durney
on: 02-02-2024
"""

import numpy as np
import pandas as pd

from komanawa.komanawa_nz_depth_to_water.head_data_processing.data_processing_functions import (find_overlapping_files,
                                                                                                copy_with_prompt,
                                                                                                _get_summary_stats,
                                                                                                append_to_other,
                                                                                                needed_cols_and_types,
                                                                                                data_checks,
                                                                                                metadata_checks,
                                                                                                renew_hdf5_store,
                                                                                                get_hdf5_store_keys,
                                                                                                pull_tethys_data_store,
                                                                                                assign_flags_based_on_null_values,
                                                                                                aggregate_water_data)
from komanawa.komanawa_nz_depth_to_water.head_data_processing.merge_rows import merge_rows_if_possible
from komanawa.komanawa_nz_depth_to_water.project_base import groundwater_data, unbacked_dir


def get_final_nelson_data(local_paths, recalc=False):
    """
    A function that gets and returns the final ECan datasets, both the GWL and the metadata
    :param recalc: boolean, if True, the data will be recalculated
    :param save: boolean, if True, the data will be saved to the google drive
    :return: (final_cleaned_metadata, final_cleaned_gwl) both pd.DataFrame
    """
    recalc_path = local_paths['save_path']
    if recalc_path.exists() and not recalc:
        metadata = pd.read_hdf(recalc_path, local_paths['nelson_metadata_store_key'])
        water_data = pd.read_hdf(recalc_path, local_paths['wl_store_key'])
    else:
        # reading in the final data
        metadata, water_data = get_nelson_data(local_paths)

        renew_hdf5_store(local_paths['save_path'], local_paths['wl_store_key'], water_data)
        renew_hdf5_store(local_paths['save_path'], local_paths['ecan_metadata_store_key'], metadata)

    return {'combined_metadata': metadata, 'combined_water_data': water_data}

def get_nelson_data(local_paths,meta_data_requirements):
    """
    A function that reads in the metadata from the ECan datasets
    :param local_paths: dictionary, containing the paths to the local data
    :return: pd.DataFrame
    """

    needed_gw_columns = ['well_name', 'date', 'depth_to_water', 'gw_elevation', 'dtw_flag', 'water_elev_flag',
                         'data_source', 'elevation_datum', 'other']

    needed_gw_columns_type = {'well_name': "str", 'depth_to_water': "float", 'gw_elevation': "float",
                              'dtw_flag': "int",
                              'water_elev_flag': 'int',
                              'data_source': 'str', 'elevation_datum': "str", 'other': "str"}

    # Read in the metadata
    metadata = pd.read_csv(local_paths['local_path'].joinpath('Groundwater bore dips and locations for Data request.csv'))
    # return unique sites in records
    metadata = metadata.drop_duplicates(subset=['Site Name'])
    metadata = metadata.dropna(subset=['Site Name'])
    metadata = metadata.rename(columns={'Site Name': 'well_name', 'x': 'nztm_x', 'y': 'nztm_y'})
    # seperate the data in bore depth if known column by "," creating seperate column for each delimeter. some data has no delimeter and needs splittiing on 'Bore' or "Diameter"
    # Clean and split the 'Bore depth if known' column into 'Bore depth if known' and 'Diameter'
    # Replace all known delimiters (',' or words like 'Bore', 'Diameter') with a single comma
    # Use regex to ignore text prior to 'depth' and replace other known words with commas
    metadata['Bore depth if known'] = metadata['Bore depth if known'].str.replace(r'^.*depth', 'depth', regex=True)
    metadata['Bore depth if known'] = metadata['Bore depth if known'].replace(['Bore', 'Diameter'], ',', regex=True)

    # Split the cleaned string into two columns
    metadata[['Bore depth if known', 'other']] = metadata['Bore depth if known'].str.split(',', n=1, expand=True)
    metadata[['Bore depth if known']] = metadata[['Bore depth if known']].replace(['depth','is',' ','m'], '', regex=True)
    metadata[['other']] = metadata[['other']].replace([','], 'diameter', regex=True)
    metadata[['well_name']] = metadata[['well_name']].replace([' '], '_', regex=True)
    metadata['source'] = 'ncc'
    # create site name by combining well_name and source
    metadata['site_name'] = metadata['well_name'] + '_' + metadata['source']

    wl_data = pd.read_csv(local_paths['local_path'].joinpath('Groundwater bore dips and locations for Data request.csv'))
    wl_data_columns= wl_data.columns.str.strip().str.lower().str.replace(' ', '_')
    wl_data.columns = wl_data_columns
    wl_data = wl_data.rename(columns={'site_name': 'well_name', 'time': 'date', 'groundwater_level': 'depth_to_water'})
    wl_data['data_source'] = 'ncc'
    wl_data['well_name']= wl_data['well_name'].str.replace(' ', '_')
    wl_data['site_name'] = wl_data['well_name'] + '_' + wl_data['data_source']
    wl_data['date'] = pd.to_datetime(wl_data['date'], dayfirst=True, errors='coerce')
    wl_data = wl_data.dropna(subset=['site_name'])
    wl_data = wl_data[['site_name', 'well_name', 'date', 'depth_to_water']]
    wl_data['date'] = pd.to_datetime(wl_data['date'].dt.date)
    wl_data['gw_elevation'] = np.nan
    # Convert the 'depth_to_water' column to a numeric type
    wl_data['depth_to_water'] = pd.to_numeric(wl_data['depth_to_water'], errors='coerce')

    # Divide 'depth_to_water' values by 1000
    wl_data['depth_to_water'] = wl_data['depth_to_water'] / 1000

    assign_flags_based_on_null_values(wl_data, 'depth_to_water', 'dtw_flag', 1, 0)
    # Assign 'water_elev_flag' based on 'gw_elevation'
    assign_flags_based_on_null_values(wl_data, 'gw_elevation', 'water_elev_flag', 1, 0)

    for col in meta_data_requirements['needed_columns']:
        if col not in tethys_metadata_all.columns:
            tethys_metadata_all[col] = meta_data_requirements['default_values'].get(col)

    for col, dtype in meta_data_requirements['col_types'].items():
        tethys_metadata_all[col] = tethys_metadata_all[col].astype(dtype)
    if 'other' not in tethys_metadata_all.columns:
        tethys_metadata_all['other'] = ''



    return metadata


def _get_folder_and_local_paths(source_dir, local_dir, redownload=False):
    """This function reads in the file paths and creates local directories"""
    # Source directory based on the provided 'directory' parameter
    local_base_path = local_dir
    src_dir = groundwater_data.joinpath(source_dir)
    dst_dir = local_dir.joinpath(src_dir.name)
    # Initialize the local directory map
    local_dir_map = {}

    # Determine the destination directory

    if redownload:
        if src_dir.is_file():
            overlapping_items = [dst_dir] if dst_dir.exists() else []
        else:
            overlapping_items = find_overlapping_files(src_dir, dst_dir)
        copy_with_prompt(src_dir, dst_dir, overlapping_items)

    local_dir_map[src_dir.name] = dst_dir

    # Construct paths for specific data within the local directory
    local_path_mapping = local_dir_map.get(src_dir.name)
    local_paths = {
        'nelson_local_save_path': local_base_path.joinpath("gwl_ecan", "cleaned_data", "nelson_gw_data.hdf"),
        'local_path': local_path_mapping
    }

    # Store keys are hardcoded as they are specific to this setup
    local_paths['wl_store_key'] = 'nelson_gwl_data'
    local_paths['ecan_metadata_store_key'] = 'nelson_metadata'
    local_paths['save_path'] = groundwater_data.joinpath('gwl_nelson', 'From_nelson', 'cleaned_data',
                                                         'combined_nelson_data.hdf')

    return local_paths


def get_nelson_data(recalc=False, redownload=False):
    local_paths = _get_folder_and_local_paths(source_dir=groundwater_data.joinpath('gwl_nelson'),
                                              local_dir=unbacked_dir.joinpath('nelson_working/'), redownload=redownload)
    meta_data_requirements = needed_cols_and_types('ncc')
    get_nelson_data(local_paths, meta_data_requirements)

    return get_final_nelson_data(local_paths,
                               recalc=recalc)


if __name__ == '__main__':

    out = get_nelson_data(recalc=True, redownload=False)
    pass
