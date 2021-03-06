"""A django model friendly wrapper around the fast grow binary"""
import json
import logging
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from django.db import transaction
from fast_grow_server.settings import DATABASES
from fast_grow.settings import FAST_GROW, CHUNK_SIZE
from fast_grow.models import Hit


class FastGrowWrapper:
    """A django model friendly wrapper around the fast grow binary"""

    @staticmethod
    def grow(growing):
        """Perform a growing according to the options in the growing model

        :param growing: growing model that defines the growing
        :type growing: fast_grow.models.Growing
        """
        core_file = growing.core.write_temp()
        database_name = growing.fragment_set.name
        with TemporaryDirectory() as directory:
            hits_path = Path(directory) / 'hits.sdf'
            args = [
                FAST_GROW,
                '--ligand', core_file.name,
                '--results', str(hits_path),
                '--database', database_name,
                '--chunksize', str(CHUNK_SIZE),
                '--writemode', '1',
                '--databasetype', '0',
                '--username', DATABASES['default']['USER'],
                '--port', DATABASES['default']['PORT'],
                '--host', DATABASES['default']['HOST']
            ]
            ensemble_dir = growing.ensemble.write_temp()
            args.extend(['--ensemble', ensemble_dir.name])
            if growing.search_points:
                search_points_file = FastGrowWrapper.write_temp_search_points(growing.search_points)
                args.extend(['--interactions', search_points_file.name])
            logging.info(' '.join(args))
            process = subprocess.Popen(args)
            seen = set()
            while True:
                FastGrowWrapper.process_hits(growing, directory, seen)
                time.sleep(1)
                if process.poll() is not None:
                    break
            FastGrowWrapper.process_hits(growing, directory, seen)

            if process.returncode > 0:
                stdout, stderr = process.communicate()
                raise subprocess.CalledProcessError(
                    process.returncode, args, output=stdout, stderr=stderr)

    @staticmethod
    def write_temp_search_points(search_points):
        """Write a search points query file

        :param search_points: search points to write
        :type search_points: str
        :return: temporary search point file
        :rtype: File
        """
        temp_file = NamedTemporaryFile(mode='w+', suffix='search_points.json')
        json.dump({'query': json.loads(search_points)}, temp_file)
        temp_file.seek(0)
        return temp_file

    @staticmethod
    def process_hits(growing, directory_path, seen_files):
        """Process unseen hit files

        :param growing: growing to save hits to
        :type growing: fast_grow.models.Growing
        :param directory_path: path to hits files
        :type directory_path: str
        :param seen_files: hits files already processed
        :type seen_files: set
        """
        with transaction.atomic():
            for hit_file in Path(directory_path).glob('*.sdf'):
                if hit_file not in seen_files:
                    FastGrowWrapper.add_hits(growing, hit_file)
                    seen_files.add(hit_file)

    @staticmethod
    def add_hits(growing, hits_path):
        """Add hits from a hits file to a growing

        :param growing: growing to add hits to
        :type growing: fast_grow.models.Growing
        :param hits_path: path to hits file
        :type hits_path: str
        """
        with open(hits_path, encoding='utf8') as hits_file:
            data = hits_file.read()
        mol_strings = [m + '$$$$\n' for m in data.split('$$$$\n') if m.strip()]
        for mol_string in mol_strings:
            hit_name = FastGrowWrapper.get_mol_string_name(mol_string)[:254]
            hit_score = FastGrowWrapper.get_mol_string_prop('Score', mol_string, cast_to=float)
            ensemble_scores = {}
            if growing.ensemble.complex_set.count() > 1:
                for cmplx in growing.ensemble.complex_set.all():
                    ensemble_scores[cmplx.name] = \
                        FastGrowWrapper.get_mol_string_prop(cmplx.name.upper(), mol_string, cast_to=float)
            hit = Hit(
                growing=growing,
                name=hit_name,
                score=hit_score,
                file_string=mol_string,
                file_type='sdf',
                ensemble_scores=ensemble_scores
            )
            hit.save()

    @staticmethod
    def get_mol_string_name(mol_string):
        """get the mol name out of an SDF string

        :param mol_string: string of an SDF
        :type mol_string: str
        :return: name of the mol in the SDF
        :rtype: str
        """
        return mol_string.split('\n')[0].strip()

    @staticmethod
    def get_mol_string_prop(prop, mol_string, cast_to=None):
        """get a property out of an SDF mol string

        :param prop: property to extract
        :type prop: str
        :param mol_string: string of an SDF
        :type mol_string: str
        :param cast_to: type to cast prop to
        :return: property
        """
        for element in mol_string.split('> <'):
            property_pair = [e.strip() for e in element.replace('$$$$', '').split('>\n')]
            if property_pair[0] != prop:
                continue
            if cast_to is not None:
                property_pair[1] = cast_to(property_pair[1])
            return property_pair[1]
        return None
