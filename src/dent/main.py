''' dent - "Enter" a Docker container, with optional container/image creation

    For detailed documenation, see the README file. If you do not have
    the full repo, you can find it at <https://github.com/cynic-net/dent/>.
'''

from    dent  import configure, container, image
from    dent.util  import die

def main():
    conf = configure.parseargs()

    #   If we know the given base image name, get any special configuration
    #   for it. Otherwise we use a generic config.
    image.IMAGE_CONF = image.BASE_IMAGES.get(conf.base_image) or {}

    if conf.print_file and conf.CONTAINER_NAME:
        print(image.PRINT_FILE_ARGS[conf.print_file](conf))
    elif conf.CONTAINER_NAME:
        return container.enter_container(conf)
    else:
        die('Internal argument parsing error.')     # Should never happen.
