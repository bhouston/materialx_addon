#!/usr/bin/env python3
"""
Blender MaterialX Exporter

A Python script that exports Blender materials to MaterialX (.mtlx) format,
replicating the functionality of Blender's C++ MaterialX exporter.

Usage:
    import blender_materialx_exporter as mtlx_exporter
    mtlx_exporter.export_material_to_materialx(material, "output.mtlx")
"""

import bpy
import os
import shutil
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import math


class MaterialXBuilder:
    """Builds MaterialX XML documents."""
    
    def __init__(self, material_name: str, logger, version: str = "1.38" ):
        self.material_name = material_name
        self.version = version
        self.node_counter = 0
        self.nodes = {}
        self.connections = []
        self.logger = logger

        # Create root element
        self.root = ET.Element("materialx")
        self.root.set("version", version)
        
        # Create material first (outside nodegraph)
        self.material = ET.SubElement(self.root, "surfacematerial")
        self.material.set("name", material_name)
        self.material.set("type", "material")
        
        # Create nodegraph
        self.nodegraph = ET.SubElement(self.root, "nodegraph")
        self.nodegraph.set("name", material_name)
    
    def add_node(self, node_type: str, name: str, node_type_category: str = None, **params) -> str:
        """Add a node to the nodegraph."""
        if not name:
            name = f"{node_type}_{self.node_counter}"
            self.node_counter += 1
        
        node = ET.SubElement(self.nodegraph, node_type)
        node.set("name", name)
        if node_type_category:
            node.set("type", node_type_category)
        
        # Add parameters
        for param_name, param_value in params.items():
            if param_value is not None:
                input_elem = ET.SubElement(node, "input")
                input_elem.set("name", param_name)
                input_elem.set("type", self._get_param_type(param_value))
                input_elem.set("value", self._format_value(param_value))
        
        self.nodes[name] = node
        return name
    
    def add_connection(self, from_node: str, from_output: str, to_node: str, to_input: str):
        """Add a connection between nodes using input tags with nodename."""
        self.logger.debug(f"    *** ADDING CONNECTION: {from_node}.{from_output} -> {to_node}.{to_input} ***")
        
        # Find the target node
        target_node = self.nodes.get(to_node)
        if target_node is None:
            self.logger.warning(f"Warning: Target node '{to_node}' not found for connection")
            return
        
        # Create input element
        input_elem = ET.SubElement(target_node, "input")
        input_elem.set("name", to_input)
        
        # Determine the appropriate type based on the input name
        input_type = self._get_input_type(to_input)
        input_elem.set("type", input_type)
        input_elem.set("nodename", from_node)
        
        # Store connection info for later processing
        self.connections.append((from_node, from_output, to_node, to_input))
        self.logger.debug(f"    *** CONNECTION ADDED SUCCESSFULLY ***")
    
    def add_surface_shader_node(self, node_type: str, name: str, **params) -> str:
        """Add a surface shader node outside the nodegraph."""
        if not name:
            name = f"{node_type}_{self.node_counter}"
            self.node_counter += 1
        
        node = ET.SubElement(self.root, node_type)
        node.set("name", name)
        node.set("type", "surfaceshader")
        
        # Add parameters
        for param_name, param_value in params.items():
            if param_value is not None:
                input_elem = ET.SubElement(node, "input")
                input_elem.set("name", param_name)
                input_elem.set("type", self._get_param_type(param_value))
                input_elem.set("value", self._format_value(param_value))
        
        self.nodes[name] = node
        return name
    
    def add_surface_shader_input(self, surface_node_name: str, input_name: str, input_type: str, nodegraph_name: str = None, nodename: str = None, value: str = None):
        """Add an input to a surface shader node."""
        surface_node = self.nodes.get(surface_node_name)
        if surface_node is None:
            self.logger.warning(f"Warning: Surface shader node '{surface_node_name}' not found")
            return
        
        input_elem = ET.SubElement(surface_node, "input")
        input_elem.set("name", input_name)
        input_elem.set("type", input_type)
        
        if nodegraph_name:
            input_elem.set("output", input_name)  # Use the input name as the output name
            input_elem.set("nodegraph", nodegraph_name)
        elif nodename:
            input_elem.set("nodename", nodename)
        elif value:
            input_elem.set("value", value)
    
    def add_output(self, name: str, output_type: str, nodename: str):
        """Add an output node to the nodegraph."""
        output = ET.SubElement(self.nodegraph, "output")
        output.set("name", name)
        output.set("type", output_type)
        output.set("nodename", nodename)
    
    def set_material_surface(self, surface_node_name: str):
        """Set the surface shader for the material."""
        input_elem = ET.SubElement(self.material, "input")
        input_elem.set("name", "surfaceshader")
        input_elem.set("type", "surfaceshader")
        input_elem.set("nodename", surface_node_name)
    
    def _get_param_type(self, value) -> str:
        """Determine the MaterialX type for a value."""
        if isinstance(value, (int, float)):
            return "float"
        elif isinstance(value, (list, tuple)):
            if len(value) == 2:
                return "vector2"
            elif len(value) == 3:
                return "color3"
            elif len(value) == 4:
                return "color4"
        return "string"
    
    def _format_value(self, value) -> str:
        """Format a value for MaterialX XML."""
        if isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        else:
            return str(value)
    
    def _get_input_type(self, input_name: str) -> str:
        """Determine the appropriate type for an input based on its name."""
        # Map common input names to their expected types
        type_mapping = {
            'texcoord': 'vector2',
            'in': 'color3',
            'in1': 'color3',
            'in2': 'color3',
            'a': 'color3',
            'b': 'color3',
            'factor': 'float',
            'scale': 'float',
            'strength': 'float',
            'amount': 'float',
            'pivot': 'vector2',
            'translate': 'vector2',
            'rotate': 'float',
            'file': 'filename',
            'default': 'color3',
        }
        
        return type_mapping.get(input_name.lower(), 'color3')
    
    def to_string(self) -> str:
        """Convert the document to a formatted XML string."""
        rough_string = ET.tostring(self.root, 'unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")


class NodeMapper:
    """Maps Blender nodes to MaterialX nodes."""
    
    @staticmethod
    def get_node_mapper(node_type: str):
        """Get the appropriate mapper for a node type."""
        mappers = {
            'BSDF_PRINCIPLED': NodeMapper.map_principled_bsdf,
            'TEX_IMAGE': NodeMapper.map_image_texture,
            'TEX_COORD': NodeMapper.map_tex_coord,
            'RGB': NodeMapper.map_rgb,
            'VALUE': NodeMapper.map_value,
            'NORMAL_MAP': NodeMapper.map_normal_map,
            'VECTOR_MATH': NodeMapper.map_vector_math,
            'MATH': NodeMapper.map_math,
            'MIX': NodeMapper.map_mix,
            'INVERT': NodeMapper.map_invert,
            'SEPARATE_COLOR': NodeMapper.map_separate_color,
            'COMBINE_COLOR': NodeMapper.map_combine_color,
            'BUMP': NodeMapper.map_bump,
            'TEX_CHECKER': NodeMapper.map_checker_texture,
            'TEX_GRADIENT': NodeMapper.map_gradient_texture,
            'TEX_NOISE': NodeMapper.map_noise_texture,
            'MAPPING': NodeMapper.map_mapping,
            'LAYER': NodeMapper.map_layer,
            'ADD': NodeMapper.map_add,
            'MULTIPLY': NodeMapper.map_multiply,
            'ROUGHNESS_ANISOTROPY': NodeMapper.map_roughness_anisotropy,
            'ARTISTIC_IOR': NodeMapper.map_artistic_ior,
        }
        return mappers.get(node_type)
    
    @staticmethod
    def map_principled_bsdf(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Principled BSDF node to standard_surface."""
        node_name = builder.add_surface_shader_node("standard_surface", f"surface_{node.name}")
        
        # Map inputs to standard_surface parameters with their types
        input_mappings = {
            'Base Color': ('base_color', 'color3'),
            'Metallic': ('metallic', 'float'),
            'Roughness': ('roughness', 'float'),
            'Specular': ('specular', 'float'),
            'IOR': ('ior', 'float'),
            'Transmission': ('transmission', 'float'),
            'Alpha': ('opacity', 'float'),
            'Normal': ('normal', 'vector3'),
            'Emission Color': ('emission_color', 'color3'),
            'Emission Strength': ('emission', 'float'),
            'Subsurface': ('subsurface', 'float'),
            'Subsurface Radius': ('subsurface_radius', 'color3'),
            'Subsurface Scale': ('subsurface_scale', 'float'),
            'Subsurface Anisotropy': ('subsurface_anisotropy', 'float'),
            'Sheen': ('sheen', 'float'),
            'Sheen Tint': ('sheen_tint', 'float'),
            'Sheen Roughness': ('sheen_roughness', 'float'),
            'Clearcoat': ('clearcoat', 'float'),
            'Clearcoat Roughness': ('clearcoat_roughness', 'float'),
            'Clearcoat IOR': ('clearcoat_ior', 'float'),
            'Clearcoat Normal': ('clearcoat_normal', 'vector3'),
            'Tangent': ('tangent', 'vector3'),
            'Anisotropic': ('anisotropic', 'float'),
            'Anisotropic Rotation': ('anisotropic_rotation', 'float'),
        }
        
        for input_name, (mtlx_param, param_type) in input_mappings.items():
            if input_name in input_nodes:
                # Add an output to the nodegraph for this parameter
                builder.add_output(mtlx_param, param_type, input_nodes[input_name])
                # Reference the nodegraph output from the surface shader
                builder.add_surface_shader_input(
                    node_name, mtlx_param, param_type, 
                    nodegraph_name=builder.material_name
                )
        
        return node_name
    
    @staticmethod
    def map_image_texture(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Image Texture node to MaterialX image node."""
        node_name = builder.add_node("image", f"image_{node.name}", "color3")
        
        # Handle image file
        if node.image:
            image_path = node.image.filepath
            if image_path:
                # Use the relative path from the .mtlx file to the texture
                exporter = getattr(builder, 'exporter', None)
                if exporter and image_path in exporter.texture_paths:
                    rel_path = exporter.texture_paths[image_path]
                else:
                    rel_path = os.path.basename(image_path)
                input_elem = ET.SubElement(builder.nodes[node_name], "input")
                input_elem.set("name", "file")
                input_elem.set("type", "filename")
                input_elem.set("value", rel_path)
        
        # Handle UV coordinates
        if 'Vector' in input_nodes:
            builder.add_connection(
                input_nodes['Vector'], "out",
                node_name, "texcoord"
            )
        
        return node_name
    
    @staticmethod
    def map_tex_coord(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Texture Coordinate node to MaterialX texcoord node."""
        node_name = builder.add_node("texcoord", f"texcoord_{node.name}", "vector2")
        return node_name
    
    @staticmethod
    def map_rgb(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map RGB node to MaterialX constant node."""
        color = [node.outputs[0].default_value[0], 
                node.outputs[0].default_value[1], 
                node.outputs[0].default_value[2]]
        node_name = builder.add_node("constant", f"rgb_{node.name}", "color3", value=color)
        return node_name
    
    @staticmethod
    def map_value(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Value node to MaterialX constant node."""
        value = node.outputs[0].default_value
        node_name = builder.add_node("constant", f"value_{node.name}", "float", value=value)
        return node_name
    
    @staticmethod
    def map_normal_map(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Normal Map node to MaterialX normalmap node."""
        node_name = builder.add_node("normalmap", f"normalmap_{node.name}", "vector3")
        
        # Handle color input
        if 'Color' in input_nodes:
            builder.add_connection(
                input_nodes['Color'], "out",
                node_name, "in"
            )
        
        # Handle strength
        if 'Strength' in input_nodes:
            builder.add_connection(
                input_nodes['Strength'], "out",
                node_name, "scale"
            )
        
        return node_name
    
    @staticmethod
    def map_vector_math(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Vector Math node to MaterialX math nodes."""
        operation = node.operation.lower()
        
        # Map operations to MaterialX node types
        operation_map = {
            'add': 'add',
            'subtract': 'subtract',
            'multiply': 'multiply',
            'divide': 'divide',
            'cross_product': 'crossproduct',
            'dot_product': 'dotproduct',
            'normalize': 'normalize',
            'length': 'magnitude',
            'distance': 'distance',
            'reflect': 'reflect',
            'refract': 'refract',
        }
        
        mtlx_operation = operation_map.get(operation, 'add')
        node_name = builder.add_node(mtlx_operation, f"vector_math_{node.name}", "vector3")
        
        # Handle inputs - use correct MaterialX parameter names
        if mtlx_operation in ['add', 'subtract', 'multiply', 'divide']:
            # These operations use in1, in2
            for i, input_name in enumerate(['A', 'B']):
                if input_name in input_nodes:
                    builder.add_connection(
                        input_nodes[input_name], "out",
                        node_name, f"in{i+1}"
                    )
        else:
            # Other operations use different parameter names
            if 'A' in input_nodes:
                builder.add_connection(
                    input_nodes['A'], "out",
                    node_name, "in1"
                )
            if 'B' in input_nodes:
                builder.add_connection(
                    input_nodes['B'], "out",
                    node_name, "in2"
                )
        
        return node_name
    
    @staticmethod
    def map_math(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Math node to MaterialX math nodes."""
        operation = node.operation.lower()
        
        # Map operations to MaterialX node types
        operation_map = {
            'add': 'add',
            'subtract': 'subtract',
            'multiply': 'multiply',
            'divide': 'divide',
            'power': 'power',
            'logarithm': 'log',
            'square_root': 'sqrt',
            'absolute': 'abs',
            'minimum': 'min',
            'maximum': 'max',
            'sine': 'sin',
            'cosine': 'cos',
            'tangent': 'tan',
            'arcsine': 'asin',
            'arccosine': 'acos',
            'arctangent': 'atan2',
            'floor': 'floor',
            'ceil': 'ceil',
            'modulo': 'modulo',
            'round': 'round',
            'sign': 'sign',
            'compare': 'compare',
        }
        
        mtlx_operation = operation_map.get(operation, 'add')
        node_name = builder.add_node(mtlx_operation, f"math_{node.name}", "float")
        
        # Handle inputs - use correct MaterialX parameter names
        if mtlx_operation in ['add', 'subtract', 'multiply', 'divide']:
            # These operations use in1, in2
            # Use input_nodes_by_index if available to handle duplicate input names
            if input_nodes_by_index:
                builder.logger.debug(f"    Using input_nodes_by_index: {input_nodes_by_index}")
                if 0 in input_nodes_by_index:  # First input (A)
                    builder.logger.debug(f"    Adding connection from {input_nodes_by_index[0]} to {node_name}.in1")
                    builder.add_connection(
                        input_nodes_by_index[0], "out",
                        node_name, "in1"
                    )
                if 1 in input_nodes_by_index:  # Second input (B)
                    builder.logger.debug(f"    Adding connection from {input_nodes_by_index[1]} to {node_name}.in2")
                    builder.add_connection(
                        input_nodes_by_index[1], "out",
                        node_name, "in2"
                    )
            else:
                # Fallback to original method
                builder.logger.debug(f"    Using fallback method with input_nodes: {input_nodes}")
                for i, input_name in enumerate(['A', 'B']):
                    if input_name in input_nodes:
                        builder.add_connection(
                            input_nodes[input_name], "out",
                            node_name, f"in{i+1}"
                        )
        else:
            # Other operations use different parameter names
            if input_nodes_by_index:
                if 0 in input_nodes_by_index:  # First input (A)
                    builder.add_connection(
                        input_nodes_by_index[0], "out",
                        node_name, "in1"
                    )
                if 1 in input_nodes_by_index:  # Second input (B)
                    builder.add_connection(
                        input_nodes_by_index[1], "out",
                        node_name, "in2"
                    )
            else:
                # Fallback to original method
                if 'A' in input_nodes:
                    builder.add_connection(
                        input_nodes['A'], "out",
                        node_name, "in1"
                    )
                if 'B' in input_nodes:
                    builder.add_connection(
                        input_nodes['B'], "out",
                        node_name, "in2"
                    )
        
        return node_name
    
    @staticmethod
    def map_mix(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Mix node to MaterialX mix node."""
        node_name = builder.add_node("mix", f"mix_{node.name}", "color3")
        
        # Handle inputs - MaterialX mix node uses fg, bg, mix parameters
        if 'A' in input_nodes:
            builder.add_connection(
                input_nodes['A'], "out",
                node_name, "fg"
            )
        
        if 'B' in input_nodes:
            builder.add_connection(
                input_nodes['B'], "out",
                node_name, "bg"
            )
        
        if 'Factor' in input_nodes:
            builder.add_connection(
                input_nodes['Factor'], "out",
                node_name, "mix"
            )
        
        return node_name
    
    @staticmethod
    def map_invert(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Invert node to MaterialX invert node."""
        node_name = builder.add_node("invert", f"invert_{node.name}", "color3")
        
        if 'Color' in input_nodes:
            builder.add_connection(
                input_nodes['Color'], "out",
                node_name, "in"
            )
        
        return node_name
    
    @staticmethod
    def map_separate_color(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Separate Color node to MaterialX separate3 node."""
        node_name = builder.add_node("separate3", f"separate_{node.name}", "float")
        
        if 'Color' in input_nodes:
            builder.add_connection(
                input_nodes['Color'], "out",
                node_name, "in"
            )
        
        return node_name
    
    @staticmethod
    def map_combine_color(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Combine Color node to MaterialX combine3 node."""
        node_name = builder.add_node("combine3", f"combine_{node.name}", "color3")
        
        for input_name in ['R', 'G', 'B']:
            if input_name in input_nodes:
                builder.add_connection(
                    input_nodes[input_name], "out",
                    node_name, input_name.lower()
                )
        
        return node_name
    
    @staticmethod
    def map_bump(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Bump node to MaterialX bump node."""
        node_name = builder.add_node("bump", f"bump_{node.name}", "vector3")
        
        if 'Height' in input_nodes:
            builder.add_connection(
                input_nodes['Height'], "out",
                node_name, "in"
            )
        
        if 'Strength' in input_nodes:
            builder.add_connection(
                input_nodes['Strength'], "out",
                node_name, "scale"
            )
        
        return node_name
    
    @staticmethod
    def map_checker_texture(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Checker Texture node to MaterialX checkerboard node."""
        node_name = builder.add_node("checkerboard", f"checker_{node.name}", "color3")
        
        # Handle scale
        if 'Scale' in input_nodes:
            builder.add_connection(
                input_nodes['Scale'], "out",
                node_name, "scale"
            )
        
        return node_name
    
    @staticmethod
    def map_gradient_texture(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Gradient Texture node to MaterialX ramplr node."""
        gradient_type = node.gradient_type.lower()
        
        if gradient_type == 'linear':
            node_name = builder.add_node("ramplr", f"gradient_{node.name}", "color3")
        else:
            node_name = builder.add_node("ramptb", f"gradient_{node.name}", "color3")
        
        return node_name
    
    @staticmethod
    def map_noise_texture(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Noise Texture node to MaterialX noise nodes."""
        noise_dimensions = node.noise_dimensions
        
        if noise_dimensions == '2D':
            node_name = builder.add_node("noise2d", f"noise_{node.name}", "color3")
        else:
            node_name = builder.add_node("noise3d", f"noise_{node.name}", "color3")
        
        # Handle scale
        if 'Scale' in input_nodes:
            builder.add_connection(
                input_nodes['Scale'], "out",
                node_name, "scale"
            )
        
        return node_name
    
    @staticmethod
    def map_mapping(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Mapping node to MaterialX place2d node."""
        node_name = builder.add_node("place2d", f"mapping_{node.name}", "vector2")
        
        # Handle translation
        if 'Location' in input_nodes:
            builder.add_connection(
                input_nodes['Location'], "out",
                node_name, "translate"
            )
        
        # Handle rotation
        if 'Rotation' in input_nodes:
            builder.add_connection(
                input_nodes['Rotation'], "out",
                node_name, "rotate"
            )
        
        # Handle scale
        if 'Scale' in input_nodes:
            builder.add_connection(
                input_nodes['Scale'], "out",
                node_name, "scale"
            )
        
        return node_name
    
    @staticmethod
    def map_layer(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Layer node to MaterialX layer node for vertical layering of BSDFs."""
        node_name = builder.add_node("layer", f"layer_{node.name}", "bsdf")
        
        # Handle top BSDF
        if 'Top' in input_nodes:
            builder.add_connection(
                input_nodes['Top'], "out",
                node_name, "top"
            )
        
        # Handle base BSDF
        if 'Base' in input_nodes:
            builder.add_connection(
                input_nodes['Base'], "out",
                node_name, "base"
            )
        
        return node_name
    
    @staticmethod
    def map_add(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Add node to MaterialX add node for distribution functions."""
        node_name = builder.add_node("add", f"add_{node.name}", "bsdf")
        
        # Handle first input
        if 'A' in input_nodes:
            builder.add_connection(
                input_nodes['A'], "out",
                node_name, "in1"
            )
        
        # Handle second input
        if 'B' in input_nodes:
            builder.add_connection(
                input_nodes['B'], "out",
                node_name, "in2"
            )
        
        return node_name
    
    @staticmethod
    def map_multiply(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Multiply node to MaterialX multiply node for distribution functions."""
        node_name = builder.add_node("multiply", f"multiply_{node.name}", "bsdf")
        
        # Handle first input (distribution function)
        if 'A' in input_nodes:
            builder.add_connection(
                input_nodes['A'], "out",
                node_name, "in1"
            )
        
        # Handle second input (scaling weight)
        if 'B' in input_nodes:
            builder.add_connection(
                input_nodes['B'], "out",
                node_name, "in2"
            )
        
        return node_name
    
    @staticmethod
    def map_roughness_anisotropy(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Roughness Anisotropy node to MaterialX roughness_anisotropy utility node."""
        node_name = builder.add_node("roughness_anisotropy", f"roughness_anisotropy_{node.name}", "vector2")
        
        # Handle roughness input
        if 'Roughness' in input_nodes:
            builder.add_connection(
                input_nodes['Roughness'], "out",
                node_name, "roughness"
            )
        
        # Handle anisotropy input
        if 'Anisotropy' in input_nodes:
            builder.add_connection(
                input_nodes['Anisotropy'], "out",
                node_name, "anisotropy"
            )
        
        return node_name
    
    @staticmethod
    def map_artistic_ior(node, builder: MaterialXBuilder, input_nodes: Dict, input_nodes_by_index: Dict = None) -> str:
        """Map Artistic IOR node to MaterialX artistic_ior utility node."""
        node_name = builder.add_node("artistic_ior", f"artistic_ior_{node.name}", "vector3")
        
        # Handle reflectivity input
        if 'Reflectivity' in input_nodes:
            builder.add_connection(
                input_nodes['Reflectivity'], "out",
                node_name, "reflectivity"
            )
        
        # Handle edge color input
        if 'Edge Color' in input_nodes:
            builder.add_connection(
                input_nodes['Edge Color'], "out",
                node_name, "edge_color"
            )
        
        return node_name


class MaterialXExporter:
    """Main MaterialX exporter class."""
    
    def __init__(self, material: bpy.types.Material, output_path: str, logger, options: Dict = None):
        self.material = material
        self.output_path = Path(output_path)
        self.options = options or {}
        self.logger = logger
        # Default options
        self.active_uvmap = self.options.get('active_uvmap', 'UVMap')
        self.export_textures = self.options.get('export_textures', True)
        # Use texture_path option if provided, else default to '.' (same dir as .mtlx)
        texture_path_opt = self.options.get('texture_path', '.')
        self.texture_path = (self.output_path.parent / texture_path_opt).resolve()
        self.materialx_version = self.options.get('materialx_version', '1.38')
        self.copy_textures = self.options.get('copy_textures', True)
        self.relative_paths = True  # Always use relative paths for this workflow
        # Internal state
        self.exported_nodes = {}
        self.texture_paths = {}  # Map from image absolute path to relative path used in XML
        self.builder = None
        self.unsupported_nodes = []  # Track unsupported nodes
    
    def export(self) -> dict:
        """Export the material to MaterialX format. Returns a result dict."""
        result = {
            "success": False,
            "unsupported_nodes": [],
            "output_path": str(self.output_path),
        }
        try:
            self.logger.info(f"Starting export of material '{self.material.name}'")
            self.logger.info(f"Output path: {self.output_path}")
            self.logger.info(f"Material uses nodes: {self.material.use_nodes}")
            # Attach exporter to builder for relative path lookup
            MaterialXBuilder.exporter = self
            if not self.material.use_nodes:
                self.logger.info(f"Material '{self.material.name}' does not use nodes. Creating basic material.")
                ok = self._export_basic_material()
                result["success"] = ok
                return result
            # Find the Principled BSDF node
            principled_node = self._find_principled_bsdf_node()
            if not principled_node:
                self.logger.info(f"No Principled BSDF node found in material '{self.material.name}'")
                self.logger.info("Available node types:")
                for node in self.material.node_tree.nodes:
                    self.logger.info(f"  - {node.name}: {node.type}")
                return result
            self.logger.info(f"Found Principled BSDF node: {principled_node.name}")
            self.builder = MaterialXBuilder(self.material.name, self.logger, self.materialx_version)
            # Attach exporter to builder for relative path lookup
            self.builder.exporter = self
            self.logger.info(f"Created MaterialX builder with version {self.materialx_version}")
            self.logger.info("Starting node network export...")
            surface_node_name = self._export_node_network(principled_node)
            self.logger.info(f"Node network export completed. Surface node: {surface_node_name}")
            self.builder.set_material_surface(surface_node_name)
            self.logger.info("Set material surface shader")
            self.logger.info("Writing MaterialX file...")
            self._write_file()
            self.logger.info("File written successfully")
            if self.export_textures:
                self.logger.info("Exporting textures...")
                self._export_textures()
            if self.unsupported_nodes:
                result["unsupported_nodes"] = self.unsupported_nodes
                result["success"] = False
            else:
                result["success"] = True
            self.logger.info(f"Export result: {result}")
            return result
        except Exception as e:
            import traceback
            self.logger.error(f"ERROR: Failed to export material '{self.material.name}'")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error message: {str(e)}")
            self.logger.error("Full traceback:")
            traceback.print_exc()
            return result
    
    def _export_basic_material(self) -> bool:
        """Export a basic material without nodes."""
        self.builder = MaterialXBuilder(self.material.name, self.logger, self.materialx_version)
        
        # Create a basic standard_surface shader outside the nodegraph
        surface_node = self.builder.add_surface_shader_node("standard_surface", "surface_basic")
        
        # Add inputs with values directly
        self.builder.add_surface_shader_input(
            surface_node, "base_color", "color3",
            value=f"{self.material.diffuse_color[0]}, {self.material.diffuse_color[1]}, {self.material.diffuse_color[2]}"
        )
        self.builder.add_surface_shader_input(
            surface_node, "roughness", "float",
            value=str(self.material.roughness)
        )
        self.builder.add_surface_shader_input(
            surface_node, "metallic", "float",
            value=str(self.material.metallic)
        )
        
        self.builder.set_material_surface(surface_node)
        self._write_file()
        return True
    
    def _find_principled_bsdf_node(self) -> Optional[bpy.types.Node]:
        """Find the Principled BSDF node in the material."""
        for node in self.material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node
        return None
    
    def _export_node_network(self, output_node: bpy.types.Node) -> str:
        """Export the node network starting from the output node."""
        self.logger.info(f"Building dependencies for node: {output_node.name} ({output_node.type})")
        
        # Traverse the network and build dependencies
        dependencies = self._build_dependencies(output_node)
        self.logger.info(f"Found {len(dependencies)} nodes in dependency order:")
        for i, node in enumerate(dependencies):
            self.logger.info(f"  {i+1}. {node.name} ({node.type})")
        
        # Export nodes in dependency order
        self.logger.info("Exporting nodes in dependency order...")
        for i, node in enumerate(dependencies):
            if node not in self.exported_nodes:
                self.logger.info(f"Exporting node {i+1}/{len(dependencies)}: {node.name} ({node.type})")
                try:
                    self._export_node(node)
                    self.logger.info(f"  ✓ Successfully exported {node.name}")
                except Exception as e:
                    self.logger.error(f"  ✗ Failed to export {node.name}: {str(e)}")
                    raise
            else:
                self.logger.info(f"Skipping already exported node: {node.name}")
        
        result = self.exported_nodes[output_node]
        self.logger.info(f"Node network export completed. Final surface node: {result}")
        return result
    
    def _build_dependencies(self, output_node: bpy.types.Node) -> List[bpy.types.Node]:
        """Build a list of nodes in dependency order."""
        visited = set()
        dependencies = []
        
        def visit(node):
            if node in visited:
                return
            visited.add(node)
            
            # Visit input nodes first
            for input_socket in node.inputs:
                if input_socket.links:
                    input_node = input_socket.links[0].from_node
                    visit(input_node)
            
            dependencies.append(node)
        
        visit(output_node)
        return dependencies
    
    def _export_node(self, node: bpy.types.Node) -> str:
        """Export a single node."""
        self.logger.info(f"  Processing node: {node.name} (type: {node.type})")
        self.logger.info(f"  *** ENTERING _export_node for {node.name} ***")
        
        # Get the mapper for this node type
        mapper = NodeMapper.get_node_mapper(node.type)
        if not mapper:
            self.logger.warning(f"  Warning: No mapper found for node type '{node.type}' ({node.name})")
            self.logger.warning(f"  Available mappers: {list(NodeMapper.get_node_mapper.__defaults__ or [])}")
            return self._export_unknown_node(node)
        
        self.logger.info(f"  Found mapper for {node.type}")
        
        # Build input nodes dictionary - handle duplicate input names
        input_nodes = {}
        input_nodes_by_index = {}  # Store by index for nodes with duplicate names
        for i, input_socket in enumerate(node.inputs):
            if input_socket.links:
                input_node = input_socket.links[0].from_node
                input_nodes[input_socket.name] = self.exported_nodes.get(input_node)
                input_nodes_by_index[i] = self.exported_nodes.get(input_node)
                self.logger.info(f"    Input {i} '{input_socket.name}' connected to {input_node.name}")
        
        self.logger.info(f"  Input nodes: {list(input_nodes.keys())}")
        self.logger.info(f"  Input nodes by index: {list(input_nodes_by_index.keys())}")
        self.logger.info(f"  Input nodes by index values: {input_nodes_by_index}")
        self.logger.info(f"  *** DEBUG: Node {node.name} has {len(input_nodes_by_index)} indexed inputs ***")
        
        # Map the node
        try:
            node_name = mapper(node, self.builder, input_nodes, input_nodes_by_index)
            self.exported_nodes[node] = node_name
            self.logger.info(f"  Mapped to: {node_name}")
            return node_name
        except Exception as e:
            self.logger.error(f"  Error in mapper for {node.type}: {str(e)}")
            raise
    
    def _export_unknown_node(self, node: bpy.types.Node) -> str:
        """Export an unknown node type as a placeholder and record it."""
        self.unsupported_nodes.append({
            "name": node.name,
            "type": node.type
        })
        node_name = self.builder.add_node("constant", f"unknown_{node.name}", "color3",
                                        value=[1.0, 0.0, 1.0])  # Magenta for unknown nodes
        self.exported_nodes[node] = node_name
        return node_name
    
    def _write_file(self):
        """Write the MaterialX document to file."""
        try:
            self.logger.info(f"Ensuring output directory exists: {self.output_path.parent}")
            # Ensure output directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Writing MaterialX content to: {self.output_path}")
            # Write the file
            with open(self.output_path, 'w', encoding='utf-8') as f:
                content = self.builder.to_string()
                f.write(content)
                self.logger.info(f"Successfully wrote {len(content)} characters to file")
                
        except PermissionError as e:
            self.logger.error(f"Permission error writing file: {e}")
            self.logger.error(f"Check if you have write permissions to: {self.output_path}")
            raise
        except OSError as e:
            self.logger.error(f"OS error writing file: {e}")
            self.logger.error(f"Check if the path is valid: {self.output_path}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error writing file: {e}")
            raise
    
    def _export_textures(self):
        """Export texture files."""
        if not self.export_textures:
            return
        
        # Ensure texture directory exists
        self.texture_path.mkdir(parents=True, exist_ok=True)
        
        # Find all image textures
        for node in self.material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                self._export_texture(node.image)
    
    def _export_texture(self, image: bpy.types.Image):
        """Export a single texture file."""
        if not image.filepath:
            return
        
        source_path = Path(bpy.path.abspath(image.filepath))
        if not source_path.exists():
            self.logger.warning(f"Warning: Texture file not found: {source_path}")
            return
        
        # Compute relative path from .mtlx file to texture
        # MaterialX expects forward-slash paths. Build a relative path and
        # then normalise to POSIX style so it is portable across OSes.
        rel_path = os.path.relpath(self.texture_path / source_path.name, self.output_path.parent).replace(os.sep, '/')
        self.texture_paths[str(image.filepath)] = rel_path
        # Copy the texture (overwrite if exists)
        target_path = self.texture_path / source_path.name
        if self.copy_textures:
            try:
                shutil.copy2(source_path, target_path)
                self.logger.info(f"Copied texture: {source_path.name}")
            except Exception as e:
                self.logger.error(f"Error copying texture {source_path.name}: {str(e)}")


def export_material_to_materialx(material: bpy.types.Material, 
                                output_path: str, 
                                logger,
                                options: Dict = None) -> dict:
    """
    Export a Blender material to MaterialX format.
    Returns a dict with success, unsupported_nodes, and output_path.
    """

    logger.info("=" * 50)
    logger.info("EXPORT_MATERIAL_TO_MATERIALX: Function called")
    logger.info("=" * 50)
    logger.info(f"Material: {material.name if material else 'None'}")
    logger.info(f"Output path: {output_path}")
    logger.info(f"Options: {options}")
    
    try:
        exporter = MaterialXExporter(material, output_path, logger, options)
        logger.info("MaterialXExporter instance created successfully")
        result = exporter.export()
        logger.info(f"Export result: {result}")
        return result
    except Exception as e:
        import traceback
        logger.error(f"EXCEPTION in export_material_to_materialx: {type(e).__name__}: {str(e)}")
        logger.error("Full traceback:")
        traceback.print_exc()
        return {"success": False, "unsupported_nodes": [], "output_path": output_path}


def export_all_materials_to_materialx(output_directory: str, logger, options: Dict = None) -> Dict[str, bool]:
    """
    Export all materials in the current scene to MaterialX format.
    
    Args:
        output_directory: Directory to save .mtlx files
        options: Export options dictionary
    
    Returns:
        Dict[str, bool]: Dictionary mapping material names to success status
    """
    results = {}
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for material in bpy.data.materials:
        if material.users > 0:  # Only export materials that are actually used
            output_path = output_dir / f"{material.name}.mtlx"
            results[material.name] = export_material_to_materialx(material, str(output_path), logger, options)
    
    return results


# Example usage and testing functions
def create_test_material():
    """Create a test material for demonstration."""
    # Create a new material
    material = bpy.data.materials.new(name="TestMaterial")
    material.use_nodes = True
    
    # Get the node tree
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    
    # Clear default nodes
    nodes.clear()
    
    # Create Principled BSDF
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (0, 0)
    
    # Create RGB node for base color
    rgb = nodes.new(type='ShaderNodeRGB')
    rgb.location = (-300, 0)
    rgb.outputs[0].default_value = (0.8, 0.2, 0.2, 1.0)  # Red color
    
    # Create Value node for roughness
    roughness = nodes.new(type='ShaderNodeValue')
    roughness.location = (-300, -200)
    roughness.outputs[0].default_value = 0.5
    
    # Create Material Output
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    
    # Connect nodes
    links.new(rgb.outputs[0], principled.inputs['Base Color'])
    links.new(roughness.outputs[0], principled.inputs['Roughness'])
    links.new(principled.outputs[0], output.inputs['Surface'])
    
    return material


def test_export():
    """Test the MaterialX exporter with a simple material."""
    # Create test material
    material = create_test_material()
    
    # Export options
    options = {
        'active_uvmap': 'UVMap',
        'export_textures': False,
        'materialx_version': '1.38',
        'relative_paths': True,
    }
    
    # Export the material
    success = export_material_to_materialx(material, "test_material.mtlx", options)
    
    if success["success"]:
        logger.info("Test export successful!")
        # Clean up test material
        bpy.data.materials.remove(material)
    else:
        logger.error("Test export failed!")
        logger.error(f"Unsupported nodes: {success['unsupported_nodes']}")


if __name__ == "__main__":
    # This will run when the script is executed directly
    test_export() 