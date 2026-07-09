''' dent - "Enter" a Docker container, with optional container/image creation

    For detailed documenation, see the README file. If you do not have
    the full repo, you can find it at <https://github.com/cynic-net/dent/>.
'''

from    importlib.metadata  import version

from    dent  import configure, container, image
from    dent.configure  import Config, ListBaseImages, PrintFile, PrintVersion
from    dent.util  import PROGNAME

def main(argv:list[str]|None=None):
    match configure.parseargs(argv):
     case PrintVersion():
        print(f'{PROGNAME} version {version(PROGNAME)}')
     case ListBaseImages():
        for i in image.BASE_IMAGES: print(i)
     case PrintFile(file, base_image):
        image.IMAGE_CONF = image.BASE_IMAGES.get(base_image or '') or {}
        print(image.PRINT_FILE_ARGS[file](base_image))
     case Config() as conf:
        #   If we know the given base image name, get any special
        #   configuration for it. Otherwise we use a generic config.
        image.IMAGE_CONF \
            = image.BASE_IMAGES.get(conf.base_image or '') or {}
        return container.enter_container(conf)
