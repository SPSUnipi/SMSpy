from smspy.components import Dict
from enum import IntEnum

import netCDF4 as nc
import numpy as np
import os
from pathlib import Path
import pandas as pd

NC_DOUBLE = "f8"
NP_DOUBLE = np.float64
NC_UINT = "u4"
NP_UINT = np.uint32

dir_name = os.path.dirname(__file__)
components = pd.read_csv(os.path.join(dir_name, "components.csv"), index_col=0)


class SMSFileType(IntEnum):
    """
    File types for SMS++ files.

    Supported values
    ----------------
    eProbFile (0): Problem file: Block and Configuration
    eBlockFile (1): Block file
    eConfigFile (2): Configuration file

    """

    eProbFile = (0,)  # Problem file: Block and Configuration
    eBlockFile = 1  # Block file
    eConfigFile = 2  # Configuration file


class Variable:
    name: str
    var_type: str
    dimensions: tuple
    data: float | np.ndarray

    def __init__(
        self, name: str, var_type: str, dimensions: tuple, data: float | np.ndarray
    ):
        self.name = name
        self.var_type = var_type
        self.dimensions = dimensions
        self.data = data


class Block:
    # Class variables

    _attributes: Dict  # attributes of the block
    _dimensions: Dict  # dimensions of the block
    _variables: Dict  # variables of the block
    _groups: Dict  # groups of the block

    components: Dict  # components of the block

    # Constructor

    def __init__(
        self,
        fp: Path | str = "",
        attributes: Dict = None,
        dimensions: Dict = None,
        variables: Dict = None,
        groups: Dict = None,
    ):
        self.components = Dict(components.T.to_dict())
        if fp:
            obj = self.from_netcdf(fp)
            self._attributes = obj.attributes
            self._dimensions = obj.dimensions
            self._variables = obj.variables
            self._groups = obj.groups
        else:
            self._attributes = attributes if attributes else Dict()
            self._dimensions = dimensions if dimensions else Dict()
            self._variables = variables if variables else Dict()
            self._groups = groups if groups else Dict()

    # Properties

    @property
    def attributes(self) -> Dict:
        """Return the attributes of the block."""
        return self._attributes

    @property
    def dimensions(self) -> Dict:
        """Return the dimensions of the block."""
        return self._dimensions

    @property
    def variables(self) -> Dict:
        """Return the variables of the block."""
        return self._variables

    @property
    def groups(self) -> Dict:
        """Return the groups of the block."""
        return self._groups

    @property
    def block_type(self, ignore_missing: bool = True) -> str:
        """Return the type of the block."""
        if "type" in self.attributes:
            return self.attributes["type"]
        elif ignore_missing:
            return None
        raise AttributeError("Block type not defined.")

    @block_type.setter
    def block_type(self, block_type: str):
        """
        Set the type of the block.

        Parameters
        ----------
        block_type : str
            The type of the block.
        """
        self.attributes["type"] = block_type

    def add_attribute(self, name: str, value, force: bool = False):
        """
        Add an attribute to the block.

        Parameters
        ----------
        name : str
            The name of the attribute
        value : any
            The value of the attribute
        force : bool (default: False)
            If True, overwrite the attribute if it exists.
        """
        if not force and name in self.attributes:
            raise ValueError(f"Attribute {name} already exists.")
        self.attributes[name] = value

    def add_dimension(self, name: str, value: int, force: bool = False):
        """
        Add a dimension to the block.

        Parameters
        ----------
        name : str
            The name of the dimension
        value : int
            The value of the dimension
        force : bool (default: False)
            If True, overwrite the dimension if it exists.
        """
        if not force and name in self.dimensions:
            raise ValueError(f"Dimension {name} already exists.")
        self.dimensions[name] = value

    def add_variable(
        self,
        name: str,
        var_type: str,
        dimensions: tuple,
        data: float | np.ndarray,
        force: bool = False,
    ):
        """
        Add a variable to the block.

        Parameters
        ----------
        name : str
            The name of the variable
        var_type : str
            The type of the variable
        dimensions : tuple
            The dimensions of the variable
        data : float | np.ndarray
            The data of the variable
        force : bool (default: False)
            If True, overwrite the variable if it exists.
        """
        if not force and name in self.variables:
            raise ValueError(f"Variable {name} already exists.")
        self.variables[name] = Variable(name, var_type, dimensions, data)

    def add_group(self, name: str, **kwargs):
        """
        Add a group to the block.

        Parameters
        ----------
        name : str
            The name of the group
        kwargs : dict
            The attributes of the group.
            If the argument "group" is present, the group is set to that value.
            Otherwise, arguments are passed to the Block constructor.
        """
        force = kwargs.pop("force", False)
        if not force and name in self.groups:
            raise ValueError(f"Group {name} already exists.")
        if "group" in kwargs:
            self.groups[name] = kwargs["group"]
        else:
            self.groups[name] = Block(**kwargs)
        return self

    # Input/Output operations

    def _to_netcdf_helper(self, grp: nc.Dataset | nc.Group):
        """Helper function to recursively save a Block and its sub-blocks to NetCDF."""
        # Add the block's attributes
        for key, value in self.attributes.items():
            grp.setncattr(key, value)

        # Add the dimensions
        for key, value in self.dimensions.items():
            grp.createDimension(key, value)

        # Add the variables
        for key, value in self.variables.items():
            var = grp.createVariable(key, value.var_type, value.dimensions)
            var[:] = value.data

        # Save each sub-Block as a subgroup
        for key, sub_block in self.groups.items():
            subgrp = grp.createGroup(key)
            sub_block._to_netcdf_helper(subgrp)

    def to_netcdf(self, fp: Path | str, force: bool = False):
        """
        Write the SMSNetwork object to a netCDF4 file.

        Parameters
        ----------
        fp : Path | str
            The path to the file to write.
        force : bool (default: False)
            If True, overwrite the file if it exists.
        """
        if not force and os.path.exists(fp):
            raise FileExistsError("File already exists; reading file not implemented.")

        with nc.Dataset(fp, "w") as ds:
            self._to_netcdf_helper(ds)

    @classmethod
    def _from_netcdf(cls, grb: nc.Dataset | nc.Group):
        """Helper function to recursively load a Block and its sub-blocks from NetCDF."""
        # Create a new block
        new_block = cls()

        # Retrieve attributes
        for name in grb.ncattrs():
            new_block.add_attribute(name, grb.getncattr(name), force=True)

        # Retrieve dimensions
        for dimname, dimobj in grb.dimensions.items():
            new_block.add_dimension(dimname, dimobj.size)

        # Retrieve variables
        for varname, varobj in grb.variables.items():
            new_block.add_variable(
                varname,
                var_type=varobj.dtype,
                dimensions=varobj.dimensions,
                data=varobj[:],
            )

        # Recursively load sub-blocks
        for subgrp_name, subgrb in grb.groups.items():
            new_block.add_group(subgrp_name, group=Block._from_netcdf(subgrb))

        return new_block

    @classmethod
    def from_netcdf(cls, filename):
        """Deserialize a NetCDF file to create a Block instance with nested sub-blocks."""
        with nc.Dataset(filename, "r") as ncfile:
            return cls._from_netcdf(ncfile)

    # Functions

    def add(self, component_name, name, *args, **kwargs):
        """
        Add a new object to the block.

        Parameters
        ----------
        component_name : str
            The class name of the block
        name : str
            The name of the block
        kwargs : dict
            The attributes of the block
        """
        match component_name:
            case "Attribute":
                self.add_attribute(name, *args, **kwargs)
            case "Dimension":
                self.add_dimension(name, *args, **kwargs)
            case "Variable":
                self.add_variable(name, *args, **kwargs)
            case "Group":
                self.add_group(name, *args, **kwargs)
            case _:
                raise ValueError(f"Class {component_name} not supported.")
        return self

    # Utilities

    def remove(self, component_name: str, name: str):
        """
        Remove the object with the given name from the block.

        Parameters
        ----------
        component_name : str
            The class name of the block
        name : str
            The name of the block
        """
        self.static(component_name).pop(name)

    def static(self, component_name: str) -> Dict:
        """
        Return the Dictionary of static components for component_name.
        For example, for component_name = "attribute", the Dictionary of attributes is returned.

        Parameters
        ----------
        component_name : string

        Returns
        -------
        Dict

        """
        return getattr(self, self.components[component_name]["list_name"])


class SMSNetwork(Block):
    """
    SMSNetwork is a subclass of Block that implements the creation of a SMS problem file.
    """

    def __init__(
        self,
        fp: Path | str = "",
        file_type: SMSFileType | int = SMSFileType.eProbFile,
        **kwargs,
    ):
        """
        Initialize a SMSNetwork object with the given file type.
        """
        if fp:
            super().__init__()
            sms_network = self.from_netcdf(fp)
            self._attributes = sms_network.attributes
            self._dimensions = sms_network.dimensions
            self._variables = sms_network.variables
            self._groups = sms_network.groups
        else:
            super().__init__(**kwargs)
            self.file_type = file_type

    @property
    def file_type(self) -> SMSFileType:
        """Return the file type of the SMS file."""
        return SMSFileType(self._attributes["SMS++_file_type"])

    @file_type.setter
    def file_type(self, ft: SMSFileType | int):
        """Return the file type of the SMS file."""
        self._attributes["SMS++_file_type"] = int(ft)

    @classmethod
    def _from_netcdf(cls, ncfile: nc.Dataset):
        """Deserialize a NetCDF file to create a Block instance with nested sub-blocks."""
        blk = super()._from_netcdf(ncfile)
        file_type = ncfile.getncattr("SMS++_file_type")
        return SMSNetwork(
            file_type=file_type,
            attributes=blk.attributes,
            dimensions=blk.dimensions,
            variables=blk.variables,
            groups=blk.groups,
        )


# # n = SMSNetwork(file_type = SMSFileType.eProbFile)
# # n.to_netcdf4("test.nc", force=True)

# fp_sample = "/mnt/c/Users/Davide/git/gitunipi/SMSpp_builder/resources/smspp/microgrid_microgrid_ALL_1N.nc4"
# fp_out = "test_resave.nc4"

# n2 = SMSNetwork(fp_sample)

# n2real = nc.Dataset(fp_sample)
# print(n2.file_type)  # Output: SMSFileType.eProbFile
# n2.to_netcdf(fp_out, force=True)
# n3 = SMSNetwork(fp_out)
# print(n3.file_type)  # Output: SMSFileType.eProbFile

# n3real = nc.Dataset(fp_out)

# print(f"ncompare {fp_sample} {fp_out} --only-diffs --show-attributes --file-text subset_comparison.txt")
