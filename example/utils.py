import mrcfile

import os
from os.path import join, basename
import subprocess

from shutil import move as mv

from glob import glob

import numpy as np

from contextlib import contextmanager


@contextmanager
def cd(newdir):
    "Context manager to temporarily change the working directory"
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def save_mrc(path, data, pixel_spacing):
    """
    Save data in a mrc-file and set the pixel spacing with the `alterheader` command from IMOD.

    Parameters
    ----------
    path : str
        Path of the new file.
    data : array(float)
        The data to save.
    pixel_spacing : float
        The pixel spacing in Angstrom.
    """
    mrc = mrcfile.open(path, mode='w+')
    mrc.set_data(data)
    mrc.close()
    cmd = ["alterheader",
           "-del", "{0},{0},{0}".format(pixel_spacing),
           path]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result.check_returncode()


def remove_files(dir, extension='.mrc'):
    """
    Removes all files in a directory with the given extension.

    Parameters
    ----------
    dir : str
        The directory to clean.
    extension : str
        The file extension. Default: ``'.mrc'``
    """
    files = glob(join(dir, '*'+extension))
    for f in files:
        os.remove(f)


def modify_newst(path, bin_factor):
    """
    Modifies the bin-factor of a given newst.com file.

    Note: This will overwrite the file!

    Parameters
    ----------
    path : str
        Path to the newst.com file.
    bin_factor : int
        The new bin-factor.
    """
    f = open(path, 'r')
    content = [l.strip() for l in f]
    f.close()

    bin_fac_idx = [i for i, s in enumerate(content) if 'BinByFactor' in s][0]

    content[bin_fac_idx] = 'BinByFactor     ' + str(bin_factor)

    f = open(path, 'w')
    for l in content:
        f.writelines("%s\n" % l)
        print(l)

    f.close()


def modify_ctfcorrection(path, bin_factor, pixel_spacing):
    """
    Modifies the bin-factor of a given ctfcorrection.com file.

    Note: This will overwrite the file!

    Parameters
    ----------
    path : str
        Path to the ctfcorrection.com file.
    bin_factor : int
        The new bin-factor.
    pixel_spacing : float
        The pixel-spacing of the input tilt-angles in Angstrom.
    """
    f = open(path, 'r')
    content = [l.strip() for l in f]
    f.close()

    ps_idx = [i for i, s in enumerate(content) if 'PixelSize' in s][0]

    content[ps_idx] = 'PixelSize       ' + str(np.round(bin_factor * pixel_spacing, decimals=3))

    f = open(path, 'w')
    for l in content:
        f.writelines("%s\n" % l)
        print(l)

    f.close()



def modify_tilt(path, bin_factor, exclude_angles=[]):
    """
    Modifies the bin-factor and exclude-angles of a given tilt.com file.

    Note: This will overwrite the file!

    Parameters
    ----------
    path : str
        Path to the tilt.com file.
    bin_factor : int
        The new bin-factor.
    exclude_angles : List<int>
        List of the tilt-angles to exclude during reconstruction. Default: ``[]``
    """
    f = open(path, 'r')
    content = [l.strip() for l in f]
    f.close()

    if not ('UseGPU 0' in content):
        content.insert(len(content) - 1, 'UseGPU 0')

    binned_idx = [i for i, s in enumerate(content) if 'IMAGEBINNED' in s][0]
    content[binned_idx] = 'IMAGEBINNED ' + str(bin_factor)

    if len(exclude_angles) > 0:
        exclude_idx = [i for i, s in enumerate(content) if 'EXCLUDELIST2 ' in s]

        if len(exclude_idx) == 0:
            exclude_idx = len(content) - 1
        else:
            exclude_idx = exclude_idx[0]

        content[exclude_idx] = "EXCLUDELIST2 " + str(exclude_angles)[1:-1]

    f = open(path, 'w')
    for l in content:
        f.writelines("%s\n" % l)
        print(l)

    f.close()


def modify_com_scripts(path, bin_factor, pixel_spacing, exclude_angles=[]):
    """
    Modifies the bin-factor and exclude-angles of the newst.com, ctfcorrection.com and tilt.com scripts.

    Note: This will overwrite the files!

    Parameters
    ----------
    path : str
        Path to the parent directory of the scripts.
    bin_factor : int
        The new bin-factor.
    pixel_spacing : float
        The pixel-spacing of the input tilt-angles in Angstrom.
    exclude_angles : List<int>
        List of the tilt-angles to exclude during reconstruction. Default: ``[]``
    """
    print("Modified 'newst.com' file:")
    modify_newst(join(path, 'newst.com'), bin_factor);
    print("")
    print("------------------------------------------------------------------------")
    print("")
    print("Modified 'ctfcorrection.com' file:")
    modify_ctfcorrection(join(path, 'ctfcorrection.com'), bin_factor, pixel_spacing);
    print("")
    print("------------------------------------------------------------------------")
    print("")
    print("Modified 'tilt.com' file:")
    modify_tilt(join(path, 'tilt.com'), bin_factor, exclude_angles);


def reconstruct_tomo(path, name, dfix, init, volt=300, rotate_X=True):
    """
    Reconstruct a tomogram with IMOD-com scripts. This also applies mtffilter after ctfcorrection.

    A reconstruction log will be placed in the reconstruction-directory.

    Parameters
    ----------
    path : str
        Path to the reconstruction-directory.
    name : str
        Name of the tomogram (the prefix).
    dfix : float
        dfixed parameter of mtffilter: Fixed dose for each image of the input file, in electrons/square Angstrom
    init : float
        initial parameter of mtffilter: Dose applied before any of the images in the input file were taken
    volt : int
        volt parameter of mtffilter. Microscope voltage in kV; must be either 200 or 300. Default: ``300``
    rotate_X : bool
        If the reconstructed tomogram should be rotated 90 degree about X. Default: ``True``
    """
    with cd(path):
        mrc_files = glob('*.mrc')
        mrc_files.sort()

        with open(name + "_reconstruction.log", "a") as log:

            cmd = ['newstack'] + mrc_files + [name + '.st']
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            cmd = ['submfg', 'eraser.com']
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            mv(name + '.st', name + '_orig.st')
            mv(name + '_fixed.st', name + '.st')

            cmd = ['submfg', 'newst.com']
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            cmd = ['submfg', 'ctfcorrection.com']
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            # dose weight options should be all set or unset
            assert (dfix is None) == (init is None)

            cmd = ['mtffilter']
            if dfix is not None:
                cmd.extend(['-dfixed', str(dfix),
                            '-initial', str(init),
                            '-volt', str(volt),
                            ])
            cmd.extend([name + '_ctfcorr.ali', name + '.ali'])
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            cmd = ['submfg', 'tilt.com']
            print(" ".join(cmd))
            result = subprocess.run(cmd, stdout=log, stderr=log)
            result.check_returncode()

            if rotate_X:
                cmd = ['trimvol',
                       '-rx', name + '_full.rec',
                       name + '.rec']
                print(" ".join(cmd))
                result = subprocess.run(cmd, stdout=log, stderr=log)
                result.check_returncode()
            else:
                print('mv {0}_full.rec {0}.rec'.format(name))
                mv(name + '_full.rec', name + '.rec')

            os.remove(name + '.st')
            os.remove(name + '_full.rec')
            mv(name + '_orig.st', name + '.st')
            os.remove(name + '.ali')
            os.remove(name + '_ctfcorr.ali')

            tomName = name + '.rec'
            split_name = os.path.basename(os.path.normpath(path))
            tomRename = name + '_' + split_name + '.rec'
            mv(tomName, tomRename)

