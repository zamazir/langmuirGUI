import numpy as np

class Conversion():
    @staticmethod
    def valtoind(realtime, timearray):
        """
        Converts a real time value to an index in a given array with time
        values. This is achieved by comparing the real time value to the array
        elements and returning the index of the closest one.
        """
        return np.abs((timearray - realtime)).argmin()

    @staticmethod
    def removeNans(array, refarray=None):
        """
        Removes values from array based on the indices of NaN values in
        refarray. If refarray is not specified, NaN values are removed from
        array. Returns a numpy array.
        """
        # If refarray was passed, comparing it to None would be deprecated
        if refarray is None:
            refarray = array

        # Convert to numpy arrays
        array = np.array(array)
        refarray = np.array(refarray)

        # Arrays must have same dimensions
        if array.size != refarray.size:
            raise ValueError('Arrays must be the same size. Array with size {}'
                             'cannot be filtered based on array with size {}'
                             .format(array.size, refarray.size))
            return array

        return array[~np.isnan(refarray)]

    @classmethod
    def removeNansMutually(cls, arr1, arr2):
        arr1 = cls.removeNans(arr1, arr2)
        arr2 = cls.removeNans(arr2)
        arr2 = cls.removeNans(arr2, arr1)
        arr1 = cls.removeNans(arr1)
        return arr1, arr2
