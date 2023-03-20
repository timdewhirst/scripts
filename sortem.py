
import click
import datetime
import exiv2
import hashlib
import logging
import pathlib
from typing import Union

loglevel_map = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG
}

def get_datetime(f: pathlib.Path) -> datetime.datetime:
    '''
    get EXIF date/time from filename; don't handle exceptions, 
    let these propagate to caller
    '''
    # get EXIF
    im = exiv2.ImageFactory.open(str(f.absolute()))
    im.readMetadata()
    metadata = im.exifData()
    
    # get datetime
    try:
        dt = str(metadata['Exif.Image.DateTime'].value())
    except:
        dt = str(metadata['Exif.Photo.DateTimeOriginal'].value())
        
    return datetime.datetime.strptime(dt, '%Y:%m:%d %H:%M:%S')

def create_if_required(p : Union[pathlib.Path, str]) -> pathlib.Path:
    result = pathlib.Path(p)
    if not result.is_dir():
        if result.exists():
            logging.error(f'cannot write to {p}: already exists and is not a directory')
            return

        result.mkdir(parents=True)
        logging.info(f'created target directory {result}')

    return result
    

@click.command()
@click.option('--starting-dir', help='directory to start scanning')
@click.option('--target-dir', help='directory to move images to')
@click.option('--log-level', default='info', help='log level')
def run(starting_dir, target_dir, log_level):
    logging.getLogger().setLevel( loglevel_map[log_level] )
    
    # check if we need to create target_dir
    target = create_if_required(target_dir)
    
    # check for broken/unknown/outliers store
    outliers = create_if_required(target / 'outliers')

    # scan files first then descend into directories
    directories = [ pathlib.Path(starting_dir) ]
    while len(directories) > 0:
        d = directories.pop(0)
        logging.debug(f'processing {d.absolute()}...')
        directories += [x for x in d.iterdir() if x.is_dir()]

        # check all files:
        # - if zero sized, remove
        # - extract date from EXIF
        #   - if error, put into error directory
        # - copy file to yyyy/mm/dd
        #   - check for duplicate at filename level
        #   - if duplicate name found, check checksums
        #   - if checksums match, discard
        #   - if checksums don't match, copy and append checksum to filename
        files = [x for x in d.iterdir() if x.is_file() and not x.is_symlink()]
        for f in files:
            if logging.getLogger().level == logging.DEBUG:
                input('>')

            logging.debug(f'processing {f.absolute()}...')
            f_stat = f.stat()
            if f_stat.st_size == 0:
                # empty file - remove
                logging.debug(f'zero size; removing')
                f.unlink()
                continue

            # get datetime; if no EXIF data then move to outliers
            try:
                f_datetime = get_datetime(f.absolute())
            except Exception as e:
                logging.debug(f'{e}: failed to get EXIF data for {f.name}, moving to {outliers / f.name}')
                f.rename(outliers / f.name)
                continue

            target_dir = create_if_required(target / f'{f_datetime.year}/{f_datetime.month:02}/{f_datetime.day:02}')
            target_file = target_dir / f.name
            if target_file.exists():
                # filenames match - check hashes
                original_hash = hashlib.blake2b()
                original_hash.update(f.read_bytes())
                target_hash = hashlib.blake2b()
                target_hash.update(target_file.read_bytes())

                if original_hash.hexdigest() == target_hash.hexdigest():
                    # hashes match - put this into outliers with hash appended
                    target_file = outliers / f'{f.name}-{original_hash.hexdigest()}'
                    logging.debug(f'hash matches; moving to: {target_file.absolute()}')
                else:
                    # hashes don't match - copy to destination with hash appended
                    target_file = target_dir / f'{f.name}-{original_hash.hexdigest()}'
                    logging.debug(f"hash doesn't match; moving to: {target_file.absolute()}")

            logging.debug(f'target: {target_file.absolute()}')
            f.rename(target_file)

                
if __name__ == '__main__':
    run()
