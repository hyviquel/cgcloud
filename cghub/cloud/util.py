from StringIO import StringIO
import argparse
import os
import re
import errno
import sys

from Crypto.Hash import MD5, SHA
from Crypto.PublicKey import RSA


def unpack_singleton(singleton):
    """
    Expects a iterable with exactly one element and returns that element. If the iterable is
    empty or yields more than one element an exception will be thrown.

    >>> unpack_singleton([0])
    0

    >>> unpack_singleton([])
    Traceback (most recent call last):
    ....
    RuntimeError: Expected singleton, got empty iterable

    >>> unpack_singleton([0,1])
    Traceback (most recent call last):
    ....
    RuntimeError: Expected singleton, got iterable with more than one element
    """
    it = iter( singleton )
    try:
        result = it.next( )
    except StopIteration:
        raise RuntimeError( "Expected singleton, got empty iterable" )
    try:
        it.next( )
        raise RuntimeError( "Expected singleton, got iterable with more than one element" )
    except StopIteration:
        return result


def camel_to_snake(s, separator='_'):
    """
    Converts camel to snake case

    >>> camel_to_snake('CamelCase')
    'camel_case'

    >>> camel_to_snake('Camel_Case')
    'camel_case'

    >>> camel_to_snake('camelCase')
    'camel_case'

    >>> camel_to_snake('USA')
    'usa'

    >>> camel_to_snake('TeamUSA')
    'team_usa'

    >>> camel_to_snake('Team_USA')
    'team_usa'

    >>> camel_to_snake('R2D2')
    'r2_d2'
    """
    return re.sub( '([a-z0-9])([A-Z])', r'\1%s\2' % separator, s ).lower( )


def abreviated_snake_case_class_name(cls, root_cls):
    """
    Returns the snake-case (with '-' instead of '_') version of the name of a given class with
    the name of another class removed from the end.

    :param cls: the class whose name to abreviate

    :param root_cls: an ancestor of cls, whose name will be removed from the end of the name of cls

    :return: cls.__name__ with root_cls.__name__ removed, converted to snake case with - as the
    separator

    >>> class Dog: pass
    >>> abreviated_snake_case_class_name(Dog,Dog)
    ''
    >>> class BarkingDog(Dog): pass
    >>> abreviated_snake_case_class_name(BarkingDog,Dog)
    'barking'
    >>> class SleepingGrowlingDog(Dog): pass
    >>> abreviated_snake_case_class_name(SleepingGrowlingDog,Dog)
    'sleeping-growling'
    >>> class Lumpi(SleepingGrowlingDog): pass
    >>> abreviated_snake_case_class_name(Lumpi,Dog)
    'lumpi'
    """
    name = cls.__name__
    suffix = root_cls.__name__
    if name.endswith( suffix ): name = name[ :-len( suffix ) ]
    return camel_to_snake( name, separator='-' )


def mkdir_p(path):
    """
    The equivalent of mkdir -p
    """
    try:
        os.makedirs( path )
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir( path ):
            pass
        else:
            raise


class UserError( RuntimeError ):
    pass

class Application( object ):
    """
    An attempt at modularizing command line parsing (argparse). This is an experiment. The
    general idea is to expose an application's functionality on the command line as separate
    subcommands, each subcommmand is represented by a separate class each of which gets its own
    subparser (an argparse concept). This collects both, the subcommand's functionality and the
    code that sets up the command line interface to that functionality under the umbrella of a
    single class.

    >>> class FooCommand( Command ):
    ...     def __init__(self, app):
    ...         super( FooCommand, self ).__init__( app, help='Do some voodoo' )
    ...         self.option( '--verbose', action='store_true' )
    ...
    ...     def run(self, options):
    ...         print 'Voodoo Magic' if options.verbose else 'Juju'

    >>> app = Application()
    >>> app.add( FooCommand )
    >>> app.run( [ "foo", "--verbose" ] ) # foo is the command name
    Voodoo Magic
    >>> app.run( [ "foo" ] )
    Juju
    """

    def __init__(self):
        """
        Initializes the argument parser
        """
        super( Application, self ).__init__( )
        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        self.parser._positionals.title = 'Commands'
        self.parser._optionals.title = 'Global options'
        self.subparsers = self.parser.add_subparsers( help='Application commands',
                                                      dest='command_name' )
        self.commands = { }

    def option(self, *args, **kwargs):
        self.parser.add_argument( *args, **kwargs )

    def add(self, command_cls):
        """
        Instantiates a command of the specified class and adds it to this application.
        """
        command = command_cls( self )
        self.commands[ command.name( ) ] = command

    def run(self, args=None):
        """
        Parses the command line into an options object using arparse and invokes the requested
        command's run() method with that options object.
        """
        options = self.parser.parse_args( args )
        self.prepare( options )
        command = self.commands[ options.command_name ]
        try:
            command.run( options )
        except UserError as e:
            sys.stderr.write( e.message )
            sys.stderr.write( '\n' )
            exit( 1 )

    def prepare(self, options):
        pass


class Command( object ):
    """
    An abstract base class for an applications commands.
    """

    def run(self, options):
        """
        Execute this command.

        :param options: the parsed command line arguments
        """
        raise NotImplementedError( )

    def __init__(self, application, **kwargs):
        """
        Initializes this command.
        :param application: The application this command belongs to.
        :type application: Application
        :param kwargs: optional arguments to the argparse's add_parser() method
        """
        super( Command, self ).__init__( )
        if not 'help' in kwargs:
            kwargs[ 'help' ] = self.__class__.__doc__
        self.parser = application.subparsers.add_parser(
            self.name( ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            **kwargs )
        self.parser._positionals.title = 'Command arguments'
        self.parser._optionals.title = 'Command options'
        self.group = None

    def option(self, *args, **kwargs):
        target = self.parser if self.group is None else self.group
        target.add_argument( *args, **kwargs )

    def name(self):
        """
        Returns the name of this command as referred to by the user when invoking it via the
        command line. The command name is the snake-case version (with dashes instead of
        underscores) of this command's class name, minus its 'Command' suffix.

        >>> class FooBarCommand(Command): pass
        >>> app=Application()
        >>> FooBarCommand(app).name()
        'foo-bar'
        """
        return abreviated_snake_case_class_name( self.__class__, Command )

    def begin_mutex(self, **kwargs):
        self.group = self.parser.add_mutually_exclusive_group( **kwargs )

    def end_mutex(self):
        self.group = None


empty_line_re = re.compile( r'^\s*(#.*)$' )


def prepend_shell_script(script, in_file, out_file):
    """
    Writes all lines from the specified input to the specified output. Input and output are both
    assumed to be file-like objects. Reading from the input as well as writing to the output
    starts at the current position in the respective file-like object. Unless the given script is
    empty or None, and before writing the first script line from the input, the given script
    will be written to the output, followed by a new line.  A script line is a line that is not
    empty. An empty line is a line that contains only whitespace, a comment or both.

    >>> i,o = StringIO(''), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    'hello\\n'

    >>> i,o = StringIO(''), StringIO()
    >>> prepend_shell_script('',i,o)
    >>> o.getvalue()
    ''

    >>> i,o = StringIO('\\n'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    'hello\\n\\n'

    >>> i,o = StringIO('#foo\\n'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    '#foo\\nhello\\n'

    >>> i,o = StringIO(' # foo \\nbar\\n'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    ' # foo \\nhello\\nbar\\n'

    >>> i,o = StringIO('bar\\n'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    'hello\\nbar\\n'

    >>> i,o = StringIO('#foo'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    '#foo\\nhello\\n'

    >>> i,o = StringIO('#foo\\nbar # bla'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    '#foo\\nhello\\nbar # bla\\n'

    >>> i,o = StringIO(' bar # foo'), StringIO()
    >>> prepend_shell_script('hello',i,o)
    >>> o.getvalue()
    'hello\\n bar # foo\\n'
    """

    def write_line(line):
        out_file.write( line )
        if not line.endswith( '\n' ):
            out_file.write( '\n' )

    line = None
    for line in in_file:
        if not empty_line_re.match( line ): break
        write_line( line )
        line = None
    if script: write_line( script )
    if line: write_line( line )
    for line in in_file:
        write_line( line )


def partition_seq(seq, size):
    """
    Splits a sequence into an iterable of subsequences. All subsequences are of the given size,
    except the last one, which may be smaller. If the input list is modified while the returned
    list is processed, the behavior of the program is undefined.

    :param seq: the list to split
    :param size: the desired size of the sublists, must be > 0
    :type size: int
    :return: an iterable of sublists

    >>> list(partition_seq("",1))
    []
    >>> list(partition_seq("abcde",2))
    ['ab', 'cd', 'e']
    >>> list(partition_seq("abcd",2))
    ['ab', 'cd']
    >>> list(partition_seq("abcde",1))
    ['a', 'b', 'c', 'd', 'e']
    >>> list(partition_seq("abcde",0))
    Traceback (most recent call last):
    ...
    ValueError: Size must be greater than 0
    >>> l=[1,2,3,4]
    >>> i = iter( partition_seq(l,2) )
    >>> l.pop(0)
    1
    >>> i.next()
    [2, 3]
    """
    if size < 1:
        raise ValueError( 'Size must be greater than 0' )
    return (seq[ pos:pos + size ] for pos in xrange( 0, len( seq ), size ))


def ec2_keypair_fingerprint(ssh_key):
    """
    Computes the fingerrint of a public or private OpenSSH key in the way Amazon does it for
    keypairs resulting from either importing a SSH public key or generating a new keypair.

    :param ssh_key: a RSA public key in OpenSSH format, or an RSA private key in PEM format

    :return: The fingerprint of the key, in pairs of two hex digits with a colon between
    pairs.

    >>> ssh_pubkey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCvdDMvcwC1/5ByUhO1wh1sG6ficwgGHRab/p'+\\
    ... 'm6LN60rgxv+u2eJRao2esGB9Oyt863+HnjKj/NBdaiHTHcAHNq/TapbvEjgHaKgrVdfeMdQbJhWjJ97rql9Yn8k'+\\
    ... 'TNsXOeSyTW7rIKE0zeQkrwhsztmATumbQmJUMR7uuI31BxhQUfD/CoGZQrxFalWLDZcrcYY13ynplaNA/Hd/vP6'+\\
    ... 'qWO5WC0dTvzROEp7VwzJ7qeN2kP1JTh+kgVRoYd9mSm6x9UVjY6jQtZHa01Eg05sFraWgvNAvKhk9LS9Kiwhq8D'+\\
    ... 'xHdWdTamnGLtwXYQbn7RjG3UADAiTOWk+QSmU2igZvQ2F hannes@soe.ucsc.edu\\n'
    >>> ec2_keypair_fingerprint(ssh_pubkey)
    'a5:5a:64:8a:1e:3f:4e:46:cd:1f:e9:b3:fc:cf:c5:19'

    >>> # This is not a private key that is in use, in case you were wondering
    >>> ssh_private_key = \\
    ... '-----BEGIN RSA PRIVATE KEY-----\\n'+\\
    ... 'MIIEpQIBAAKCAQEAi3shPK00+/6dwW8u+iDkUYiwIKl/lv0Ay5IstLszwb3CA4mVRlyq769HzE8f\\n'+\\
    ... 'cnzQUX/NI8y9MTO0UNt2JDMJWW5L49jmvxV0TjxQjKg8KcNzYuHsEny3k8LxezWMsmwlrrC89O6e\\n'+\\
    ... 'oo6boc8ForSdjVdIlJbvWu/82dThyFgTjWd5B+1O93xw8/ejqY9PfZExBeqpKjm58OUByTpVhvWe\\n'+\\
    ... 'jmbZ9BL60XJhwz9bDTrlKpjcGsMZ74G6XfQAhyyqXYeD/XOercCSJgQ/QjYKcPE9yMRyucHyuYZ8\\n'+\\
    ... 'HKzmG+u4p5ffnFb43tKzWCI330JQcklhGTldyqQHDWA41mT1QMoWfwIDAQABAoIBAF50gryRWykv\\n'+\\
    ... 'cuuUfI6ciaGBXCyyPBomuUwicC3v/Au+kk1M9Y7RoFxyKb/88QHZ7kTStDwDITfZmMmM5QN8oF80\\n'+\\
    ... 'pyXkM9bBE6MLi0zFfQCXQGN9NR4L4VGqGVfjmqUVQat8Omnv0fOpeVFpXZqij3Mw4ZDmaa7+iA+H\\n'+\\
    ... '72J56ru9i9wcBNqt//Kh5BXARekp7tHzklYrlqJd03ftDRp9GTBIFAsaPClTBpnPVhwD/rAoJEhb\\n'+\\
    ... 'KM9g/EMjQ28cUMQSHSwOyi9Rg/LtwFnER4u7pnBz2tbJFvLlXE96IQbksQL6/PTJ9H6Zpp+1fDcI\\n'+\\
    ... 'k/MKSQZtQOgfV8V1wlvHX+Q0bxECgYEA4LHj6o4usINnSy4cf6BRLrCA9//ePa8UjEK2YDC5rQRV\\n'+\\
    ... 'huFWqWJJSjWI9Ofjh8mZj8NvTJa9RW4d4Rn6F7upOuAer9obwfrmi4BEQSbvUwxQIuHOZ6itH/0L\\n'+\\
    ... 'klqQBuhJeyr3W+2IhudJUQz9MEoddOfYIybXqkF7XzDl2x6FcjcCgYEAnunySmjt+983gUKK9DgK\\n'+\\
    ... '/k1ki41jCAcFlGd8MbLEWkJpwt3FJFiyq6vVptoVH8MBnVAOjDneP6YyNBv5+zm3vyMuVJtKNcAP\\n'+\\
    ... 'MAxrl5/gyIBHRxD+avoqpQX/17EmrFsbMaG8IM0ZWB2lSDt45sDvpmSlcTjzrHIEGoBbOzkOefkC\\n'+\\
    ... 'gYEAgmS5bxSz45teBjLsNuRCOGYVcdX6krFXq03LqGaeWdl6CJwcPo/bGEWZBQbM86/6fYNcw4V2\\n'+\\
    ... 'sSQGEuuQRtWQj6ogJMzd7uQ7hhkZgvWlTPyIRLXloiIw1a9zV6tWiaujeOamRaLC6AawdWikRbG9\\n'+\\
    ... 'BmrE8yFHZnY5sjQeL9q2dmECgYEAgp5w1NCirGCxUsHLTSmzf4tFlZ9FQxficjUNVBxIYJguLkny\\n'+\\
    ... '/Qka8xhuqJKgwlabQR7IlmIKV+7XXRWRx/mNGsJkFo791GhlE21iEmMLdEJcVAGX3X57BuGDhVrL\\n'+\\
    ... 'GuhX1dfGtn9e0ZqsfE7F9YWodfBMPGA/igK9dLsEQg2H5KECgYEAvlv0cPHP8wcOL3g9eWIVCXtg\\n'+\\
    ... 'aQ+KiDfk7pihLnHTJVZqXuy0lFD+O/TqxGOOQS/G4vBerrjzjCXXXxi2FN0kDJhiWlRHIQALl6rl\\n'+\\
    ... 'i2LdKfL1sk1IA5PYrj+LmBuOLpsMHnkoH+XRJWUJkLvowaJ0aSengQ2AD+icrc/EIrpcdjU=\\n'+\\
    ... '-----END RSA PRIVATE KEY-----\\n'
    >>> ec2_keypair_fingerprint(ssh_private_key)
    'ac:23:ae:c3:9a:a3:78:b1:0f:8a:31:dd:13:cc:b1:8e:fb:51:42:f8'
    """
    rsa_key = RSA.importKey( ssh_key )
    der_rsa_key = rsa_key.exportKey( format='DER', pkcs=(8 if rsa_key.has_private( ) else 1) )
    hash = (SHA if rsa_key.has_private( ) else MD5).new( )
    hash.update( der_rsa_key )
    return ':'.join( partition_seq( hash.hexdigest( ), 2 ) )


