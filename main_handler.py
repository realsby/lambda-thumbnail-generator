from __future__ import print_function
from PIL.ImageCms import profileToProfile, getProfileName
from PIL import Image, ExifTags
import tempfile
import boto3


desired_icc = "icc/sRGB_v4_ICC_preference.icc"  # Web supported icc file
target_bucket_name = 'my_thumbnails_bucket'


def lambda_handler(event, context, size=(256, 256)):
    """
    This lambda function triggered by AWS S3 when any file uploaded to media bucket,
    and tries to create thumbnails to target bucket with desired sizes.
    """
    s3_client = boto3.client('s3')
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        local_key = '/tmp/{}'.format(object_key)
        s3_client.download_file(bucket_name, object_key, local_key)

        try:
            with Image.open(open(local_key, 'rb')) as image:
                image.thumbnail(size)

                # Check and convert icc profile if required and set alpha layer
                if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                    output_mode = 'RGBA'
                else:
                    output_mode = 'RGB'

                if image.info.get('icc_profile', None):
                    try:
                        temp_icc_path = tempfile.mkstemp(suffix='.icc')[1]
                        with open(temp_icc_path, 'w+b') as image_orginal_icc:
                            image_orginal_icc.write(image.info.get('icc_profile'))
                        if not getProfileName(temp_icc_path) == getProfileName(desired_icc):
                            image = profileToProfile(image, temp_icc_path, desired_icc,
                                                     outputMode=output_mode, renderingIntent=0)
                            if output_mode == 'RGBA' and image.split()[-1]:
                                image.putalpha(image.split()[-1])
                    except Exception:
                        pass  # icc related failure is not important!
                else:
                    image = image.convert(output_mode)

                # Rotate image if required (for mostly smart phone pictures)
                for tag in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[tag] == 'Orientation':
                        break
                exif = dict(image._getexif().items())
                if exif[tag] == 3:
                    image = image.rotate(180, expand=True)
                elif exif[tag] == 6:
                    image = image.rotate(270, expand=True)
                elif exif[tag] == 8:
                    image = image.rotate(90, expand=True)
                
                thumbnail_key = '{}_resized.png'.format(local_key)
                image.save(thumbnail_key, "PNG", optimize=True,
                           dpi=[72, 72], compress_level=5, icc_profile=image.info.get('icc_profile'))
                s3_client.upload_file(thumbnail_key, target_bucket_name, '{}_resized.png'.format(object_key))
        except IOError:
            pass  # PIL could not open file as image.
