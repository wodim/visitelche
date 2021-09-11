import os
import random
import subprocess

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image


FFMPEG_CMD_VISITELCHE = (
    'ffmpeg -hide_banner '
    # first input: base video
    '-i \'{source}\' '
    # second input: images to overlay
    '-loop 1 -start_number 1 -start_number_range 8 -framerate 30 -i assets/elche_tiktok_%02d.png '
    # third input: subtitle
    '-loop 1 -framerate 30 -i assets/elche_tiktok_sub.png '
    # filter
    '-filter_complex "'
    '[0:v]fps=fps=30[base];'  # convert source to 30 fps
    '[base]scale=w=-2:h=600[base];'  # resize source to 600 px min
    '[1:v][base]scale2ref=oh*mdar:h=ih/8[logo1][base];'  # resize moving logo
    '[2:v][base]scale2ref=oh*mdar:h=ih/4[logo2][base];'  # resize subtitle
    '[logo2][logo1]overlay=0:0:eof_action=endall[logo];'  # merge both logos
    '[base][logo]overlay=0:0:eof_action=endall[v]'  # put logo over video
    # output options
    '" -map [v] -map 0:a? -c:a copy -y -preset ultrafast -crf 27 -threads 4 '
    '\'{dest}\''
)

FFMPEG_CMD_PESCANOVA = (
    'ffmpeg -hide_banner '
    # first input: base video
    '-i \'{source}\' '
    # second input: base audio
    '-i assets/pescanova.aac '
    # output options
    ' -map 0:0 -map 1:0 -c:a copy -c:v copy -shortest -y '
    '\'{dest}\''
)

FFMPEG_CMD_MEGAALVISE = (
    'ffmpeg -hide_banner -framerate 15 '
    # first input: base video
    '-pattern_type glob -i \'{source}\' '
    # output options
    ' -r 15 -shortest -y '
    '\'{dest}\''
)

MEGAALVISE_FRAME_COUNT = 50


class Composer:
    def __init__(self, filename):
        self.filename = filename
        self.bg_img = None

    def load_image(self):
        with Image(filename=self.filename) as original:
            self.bg_img = Image(original)
        # remove the alpha channel, if any
        self.bg_img.alpha_channel = False

    def save_image(self, filename):
        self.bg_img.compression_quality = 100
        self.bg_img.save(filename=filename)
        return filename

    @staticmethod
    def generate_filename(filename, i=None):
        filename = filename.replace('/', '_')
        if i is not None:
            return 'tmp/masked_%s_%03d.jpg' % (filename, i)
        return 'tmp/masked_%s' % filename

    def compose_photo_visitelche(self):
        def clamp(number, minn, maxn):
            return max(min(maxn, number), minn)

        self.load_image()
        mask_img = Image(filename='assets/elche.png')
        mask_w = (self.bg_img.width / 2) * (self.bg_img.height / self.bg_img.width)
        mask_w = clamp(mask_w, self.bg_img.width / 2.5, self.bg_img.width / 1.5)
        mask_w = int(mask_w)
        mask_h = self.bg_img.height
        mask_img.transform(resize='%dx%d' % (mask_w, mask_h))
        self.bg_img.composite(mask_img, left=self.bg_img.width - mask_w, top=0)

        return self.save_image(self.generate_filename(self.filename))

    def compose_photo_bulo(self):
        return self._compose_photo_simple(['assets/bulo%d.png' % random.randint(1, 3)])

    def compose_photo_superbulo(self):
        return self._compose_photo_simple(['assets/bulo%d.png' % i for i in range(1, 4)])

    def _compose_photo_simple(self, filenames):
        self.load_image()

        for filename in filenames:
            mask_img = Image(filename=filename)
            mask_img.transform(resize='%dx%d' % (self.bg_img.width, self.bg_img.height))
            self.bg_img.composite(mask_img, gravity='center')

        return self.save_image(self.generate_filename(self.filename))

    def compose_file_visitelche(self):
        return self._compose_file_simple(FFMPEG_CMD_VISITELCHE)

    def compose_file_pescanova(self):
        return self._compose_file_simple(FFMPEG_CMD_PESCANOVA)

    def _compose_file_simple(self, cmd):
        file_dest = self.generate_filename(self.filename)

        subprocess.call(cmd.format(source=self.filename, dest=file_dest), shell=True)
        if not os.path.exists(file_dest):
            raise ValueError('ffmpeg did not output anything')

        return file_dest

    async def compose_photo_alvise(self, text=None, **kwargs):
        self.load_image()

        frame = await self._compose_alvise(self.bg_img, text=text, count=1)
        return frame[0]

    async def compose_file_megaalvise(self, text=None, **kwargs):
        self.load_image()
        file_dest = self.generate_filename(self.filename) + '.mp4'
        glob = self.generate_filename(self.filename) + '_*.jpg'

        invalid_w, invalid_h = self.bg_img.width % 2 == 1, self.bg_img.height % 2 == 1
        if invalid_w or invalid_h:
            self.bg_img.crop(
                0, 0,
                width=self.bg_img.width - 1 if invalid_w else self.bg_img.width,
                height=self.bg_img.height - 1 if invalid_h else self.bg_img.height
            )

        await self._compose_alvise(self.bg_img, text=text, count=MEGAALVISE_FRAME_COUNT,
                                   callback=kwargs.get('callback'),
                                   callback_args=kwargs.get('callback_args'))

        if kwargs.get('callback') and kwargs.get('callback_args'):
            await kwargs.get('callback')(kwargs.get('callback_args')[0],
                                         MEGAALVISE_FRAME_COUNT, MEGAALVISE_FRAME_COUNT)

        cmd = FFMPEG_CMD_MEGAALVISE.format(source=glob, dest=file_dest)
        subprocess.call(cmd, shell=True)
        if not os.path.exists(file_dest):
            raise ValueError('ffmpeg did not output anything')

        return file_dest

    async def _compose_alvise(self, bg_img, text=None, count=1, **kwargs):
        with Drawing() as drawing:
            # fill the drawing primitives
            drawing.font = 'assets/HelveticaNeueLTCom-Md.ttf'
            drawing.gravity = 'north_west'
            drawing.fill_color = Color('#56fdb4')
            text = text if text else '@Alvisepf'

            # try to determine what a good font size would be
            string_list = text.split('\n')
            longest_string = len(max(string_list, key=len))
            line_count = len(string_list)
            drawing.font_size = max(min(bg_img.width / longest_string * 1.5, bg_img.height / line_count * 1.5), 4)

            # the drawing has some padding so ascenders and descenders do not get truncated
            metrics = drawing.get_font_metrics(bg_img, text, '\n' in text)
            mask_w_orig, mask_h_orig = metrics.text_width, metrics.text_height + metrics.descender
            mask_w, mask_h = int(mask_w_orig * 1.02), int(mask_h_orig * 1.1)
            drawing.text(int((mask_w - mask_w_orig) / 2),
                         int((mask_h - mask_h_orig) / 2), text)

            # create a mask image to draw the text on to, and...
            with Image(width=mask_w, height=mask_h) as mask_img:
                # draw the text into the mask image
                drawing.draw(mask_img)
                original_mask_img = Image(mask_img)

                frames = []
                for i in range(count):
                    mask_img = Image(original_mask_img)
                    # rotate the mask
                    mask_img.rotate(random.uniform(-35, -5))
                    # calculate what a smaller background image would look like
                    scaling_factor = random.uniform(.5, .7)
                    bg_img_scaled_w = bg_img.width * scaling_factor
                    bg_img_scaled_h = bg_img.height * scaling_factor
                    # scale the mask to fit into that smaller background image
                    mask_img.transform(resize='%dx%d' % (bg_img_scaled_w, bg_img_scaled_h))
                    # calculate a random position inside the background image for it
                    offset_left = random.randint(0, bg_img.width - mask_img.width)
                    offset_top = random.randint(0, bg_img.height - mask_img.height)
                    # and put the mask in the image
                    bg_img.composite(mask_img, left=offset_left, top=offset_top)

                    frames.append(self.save_image(self.generate_filename(self.filename, i)))

                    if kwargs.get('callback') and kwargs.get('callback_args'):
                        await kwargs.get('callback')(kwargs.get('callback_args')[0], i, count)

                original_mask_img.destroy()

        return frames
