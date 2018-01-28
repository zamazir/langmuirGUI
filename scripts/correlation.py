"""
Create correlation plots and correlation matrices for all variables in a
guilangmuir database.
"""
import argparse

import pandas as pd
import numpy as np
from matplotlib.pyplot import *

def parse_arguments():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('input', action='store', help='Database')
    return argparser.parse_args()

def find_coord_columns(df):
    columns = []
    for column in df.columns:
        if df[column].str.contains('\|').any():
            columns.append(column)
    return columns

def split_coords(df, coord=None, num_only=False):
    """
    Split columns in df containing coordinates into sub-DataFrames and convert
    them to numeric values. Convert all convertable elements in df to numeric
    values. df must be passed astype(str). Returns only numeric columns if
    num_only is true.
    """
    columns = find_coord_columns(df)
    for column in columns:
        df[column] = df[column].str.split('\|', expand=True).rename(columns={0: 'x',
                                                                         1: 'y'})
        try:
            coords = df[column].columns
        except AttributeError:
            df[column] = df[column].astype(float, errors='ignore')
        else:
            for _coord in coords:
                df[column][_coord] = df[column][_coord].astype(float, errors='coerce')
            if coord:
                df[column] = df[column][coord]

    if num_only:
        df = df.select_dtypes(include=[np.number])
    return df


def main():
    params = ['n/nGW']#, 'nbar', 'Ptot', 'N_tot', 'Ne_tot', 'D_tot', 'n/nGW']
    args = parse_arguments()
    infile = args.input
    df = pd.read_csv(infile)
    #for coord in ('x', 'y'):
    coord = 'x'
    params = [el for el in params if el in df.columns]
    for param in params:
        df2 = split_coords(df.astype(str), coord, num_only=True)
        df2[param] = df[param].astype(float)
        print df2
        pd.scatter_matrix(df2)
        title(param + ' ' + coord)
    show()

if __name__ == '__main__':
    main()
