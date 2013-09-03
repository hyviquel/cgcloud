from cghub.cloud.cloud_init_box import CloudInitBox
from cghub.cloud.yum_box import YumBox


class FedoraBox( YumBox, CloudInitBox ):
    """
    A box that boots of an official Fedora cloud AMI
    """

    def release(self):
        """
        :return: the version number of the Fedora release, e.g. 17
        :rtype: int
        """
        raise NotImplementedError

    def username(self):
        return "fedora" if self.release( ) >= 19 else "ec2-user"

    def _default_image_id(self):
        release = self.release( )
        images = self.connection.get_all_images( owners='125523088429',
                                                 filters={
                                                     'name': 'Fedora-x86_64-%i-*' % release,
                                                     'root-device-type': 'ebs' } )
        if not images:
            raise RuntimeError( "Can't find any suitable AMIs for Fedora %i" % release )
        if len( images ) > 1:
            raise RuntimeError( "Found more than one AMI for Fedora %i" % release )

        return images[ 0 ].id
