import json
import math
import os.path
import subprocess


class Registry(object):
    """
    Base type for registries.
    """

    #: Number of bits needed to represent the greatest block ID.
    max_bits = None


    def encode(self, kind, obj):
        """
        Encodes a thing to an integer ID.
        """

        raise NotImplementedError

    def decode(self, kind, val):
        """
        Decodes a thing from an integer ID.
        """

        raise NotImplementedError

    def encode_block(self, obj):
        """
        Encodes a block to an integer ID.
        """

        raise NotImplementedError

    def decode_block(self, val):
        """
        Decodes a block from an integer ID.
        """

        raise NotImplementedError

    def is_air_block(self, obj):
        """
        Returns true if the given object is considered air for lighting
        purposes.
        """

        raise NotImplementedError

class OpaqueRegistry(Registry):
    """
    Registry that passes IDs through unchanged. This is the default.
    """

    def __init__(self, max_bits):
        self.max_bits = max_bits


    def encode(self, kind, obj): return obj
    def decode(self, kind, val): return val

    def encode_block(self, obj): return obj
    def decode_block(self, val): return val
    def is_air_block(self, obj): return obj == 0


class BitShiftRegistry(OpaqueRegistry):
    """
    Registry implementing the Minecraft 1.7 - 1.12 bit-shift format for blocks.

    Blocks decode to a ``(block_id, metadata)`` pair. Items pass through
    unchanged.
    """

    max_bits = 13

    def encode_block(self, obj): return (obj[0] << 4) | obj[1]
    def decode_block(self, val): return val >> 4, val & 0x0F
    def is_air_block(self, obj): return obj[0] == 0


class LookupRegistry(Registry):
    """
    Registry implementing a dictionary lookup, recommended for 1.13+.

    Blocks decode to a ``dict`` where the only guaranteed key is ``'name'``.
    Items decode to a ``str`` name.

    Use the ``from_jar()`` or ``from_json()`` class methods to load data from
    the official server.
    """


    def __init__(self, blocks, registries):
        self.max_bits = int(math.ceil(math.log(max(blocks.keys()), 2)))

        self.decode_block_map = blocks
        self.encode_block_map = {
            frozenset(value.items()): key
            for key, value in blocks.items()}

        self.decode_map = registries
        self.encode_map = {
            registry_name: {value: key for key, value in registry.items()}
            for registry_name, registry in registries.items()}

    def encode(self, registry, obj):
        return self.encode_map[registry][obj]

    def decode(self, registry, val):
        return self.decode_map[registry][val]

    def encode_block(self, obj):
        return self.encode_block_map[frozenset(obj.items())]

    def decode_block(self, val):
        return dict(self.decode_block_map[val])

    def is_air_block(self, obj):
        for name in ('air', 'cave_air', 'void_air'):
            if obj['name'] == name:
                return True
        return False

    @classmethod
    def from_jar(cls, jar_path):
        """
        Create a ``LookupRegistry`` from a Minecraft server jar file. This
        method generates JSON files by running the Minecraft server like so::

            java -cp minecraft_server.jar net.minecraft.data.Main --reports

        It then feeds the generated JSON files to ``from_json()``.
        """

        root_path, jar_name = os.path.split(jar_path)
        reports_path = os.path.join(root_path, "generated", "reports")

        # Accept EULA
        eula_path = os.path.join(root_path, "eula.txt")
        if not os.path.exists(eula_path):
            with open(eula_path, "w") as fd:
                fd.write("eula=true\n")

        # Export reports
        if not os.path.exists(reports_path):
            subprocess.check_call(
                ["java", "-cp", jar_name, "net.minecraft.data.Main",
                 "--reports"],
                cwd=root_path)

        # Load data
        return cls.from_json(reports_path)

    @classmethod
    def from_json(cls, reports_path):
        """
        Create a ``LookupRegistry`` from JSON files generated by the official
        server.
        """

        blocks = {}
        registries_temp = {}
        registries = {}

        blocks_path = os.path.join(reports_path, "blocks.json")
        items_path = os.path.join(reports_path, "items.json")
        registries_path = os.path.join(reports_path, "registries.json")

        with open(blocks_path) as fd:
            for name, obj in json.load(fd).items():
                for state in obj['states']:
                    properties = state.get("properties", {})
                    properties['name'] = name
                    blocks[state['id']] = properties

        if os.path.exists(items_path):
            with open(items_path) as fd:
                registries_temp['minecraft:item'] = {'entries': json.load(fd)}

        if os.path.exists(registries_path):
            with open(registries_path) as fd:
                registries_temp.update(json.load(fd))

        for registry_name, registry in registries_temp.items():
            registries[registry_name] = {}
            for name, obj in registry['entries'].items():
                registries[registry_name][obj['protocol_id']] = name

        return cls(blocks, registries)