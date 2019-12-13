import asyncio
# from pprint import pprint
import os
import subprocess

from wand.image import Image
import telepot
import telepot.aio


MY_NAME = 'visitelchebot'
MY_COMMAND = '/visitelche'
MY_TOKEN = ''
MY_MASK = 'elche.png'

FFMPEG_CMD = ('ffmpeg '
              # first input: base video
              '-i \'{source}\' '
              # second input: images to overlay
              '-loop 1 -start_number 1 -start_number_range 8 -framerate 30 -i tiktok/%02d.png '
              # filter
              '-filter_complex "'
              '[0:v]fps=fps=30[in];'  # convert source to 30 fps
              '[1:v][in]scale2ref=oh*mdar:h=ih/8[logo][base];'  # resize images
              '[base][logo]overlay=0:0:eof_action=endall[v]'  # overlay images
              # output options
              '" -map [v] -map 0:a? -c:a copy -y -preset ultrafast -threads 4 '
              '\'{dest}\'')

last_msg_w_media = {}


class TelegramBot(telepot.aio.Bot):
    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)

    async def on_chat_message(self, message):
        _, chat_type, chat_id, _, _ = telepot.glance(message, long=True)
        # pprint(message)
        original_message = message

        if chat_type in self.PUBLIC_CHATS and ('photo' in message or
                                               'video' in message or
                                               'animation' in message):
            last_msg_w_media[chat_id] = message

        if chat_type in self.PRIVATE_CHATS:
            if 'reply_to_message' in message:
                message = message['reply_to_message']
            if self.is_media_message(message):
                await self.process(original_message, message)
            else:
                if self.check_mention(message) and chat_id in last_msg_w_media:
                    await self.process(original_message, last_msg_w_media[chat_id])
                else:
                    await self.send_message(message, caption='e')
        elif chat_type in self.PUBLIC_CHATS:
            if 'reply_to_message' in message:
                if self.check_mention(message):
                    message = message['reply_to_message']
                    if self.is_media_message(message):
                        await self.process(original_message, message)
                    else:
                        await self.send_message(message, caption='e')
            else:
                if self.check_mention(message):
                    if self.is_media_message(message):
                        await self.process(original_message, message)
                    else:
                        if chat_id in last_msg_w_media:
                            await self.process(original_message, last_msg_w_media[chat_id])
                        else:
                            await self.send_message(message, caption='e')

    async def process(self, original_message, message):
        if 'photo' in message:
            await self.process_photo(original_message, message)
        elif 'video' in message or 'animation' in message:
            await self.process_video(original_message, message)

    @staticmethod
    def is_media_message(message):
        return ('photo' in message or
                'video' in message or
                'animation' in message)

    async def process_photo(self, original_message, message):
        file_id = message['photo'][-1]['file_id']
        file_dest = 'tmp/%s.jpg' % file_id
        if not os.path.exists(file_dest):
            print('Downloading')
            try:
                await self.download_file(file_id, file_dest)
            except:
                await self.send_message(message, caption='no me he podido bajar la foto :(')
        print('Downloaded. Composing')
        new_filename = compose(file_dest)
        print('Composed. Sending')
        try:
            _, _, chat_id, _, msg_id = telepot.glance(message, long=True)
            await self.sendChatAction(chat_id, 'upload_photo')
            last_msg_w_media[chat_id] = await self.send_message(original_message, quote_msg_id=msg_id,
                                                                type_='photo', filename=new_filename)
        except:
            await self.send_message(message, caption='no he podido enviar la foto tuneada :(')
        print('Sent')

    async def process_video(self, original_message, message):
        if 'video' in message:
            message_video = message['video']
        elif 'animation' in message:
            message_video = message['animation']
        if message_video['file_size'] > 20 * 1024 * 1024:
            await self.send_message(message, caption='un poco grande no hijo de puta?')
        wait_msg = await self.send_message(message, caption=('vale, recibido. no me atosigues porque soy '
                                                             'un pobre procesador arm de 3€ al mes'))
        file_id = message_video['file_id']
        file_dest = 'tmp/%s.mp4' % file_id
        if not os.path.exists(file_dest):
            print('Downloading')
            try:
                await self.download_file(file_id, file_dest)
            except:
                await self.send_message(message, caption='no me he podido bajar el vídeo :(')
        print('Downloaded. Composing')
        new_filename = 'tmp/%s_.mp4' % file_id
        cmd = FFMPEG_CMD.format(source=file_dest, dest=new_filename)
        print(cmd)
        subprocess.call(cmd, shell=True)
        if not os.path.exists(new_filename):
            print('ffmpeg did not output anything')
            await self.send_message(message, caption='no he podido crear el vídeo tuneado :(')
            return
        print('Composed. Sending')
        try:
            _, _, chat_id, _, msg_id = telepot.glance(message, long=True)
            await self.sendChatAction(chat_id, 'upload_video')
            last_msg_w_media[chat_id] = await self.send_message(original_message, quote_msg_id=msg_id,
                                                                type_='file', filename=new_filename)
        except:
            await self.send_message(message, caption='no he podido enviar el vídeo tuneado :(')
        finally:
            await self.deleteMessage(telepot.message_identifier(wait_msg))
        print('Sent')

    async def send_message(self, message, caption=None, filename=None,
                           type_='text', no_preview=False,
                           quote_msg_id=None):
        """helper function to send messages to users."""
        if type_ == 'text':
            if not caption:
                raise ValueError('You need a caption parameter to send text')
            text = self.ellipsis(caption, 4096)
            return await self.sendMessage(message['chat']['id'], text,
                                          disable_web_page_preview=no_preview,
                                          reply_to_message_id=quote_msg_id)
        elif type_ == 'photo':
            if not filename:
                raise ValueError('You need a file parameter to send a photo')
            if caption:
                caption = self.ellipsis(caption, 200)
            with open(filename, 'rb') as f:
                return await self.sendPhoto(message['chat']['id'], f, caption=caption,
                                            reply_to_message_id=quote_msg_id)
        elif type_ == 'file':
            if not filename:
                raise ValueError('You need a file parameter to send a file')
            if caption:
                raise ValueError("You can't send a caption with a file")
            with open(filename, 'rb') as f:
                return await self.sendDocument(message['chat']['id'], f,
                                               reply_to_message_id=quote_msg_id)

    @staticmethod
    def check_mention(msg):
        if 'text' in msg:
            text = msg['text']
        elif 'caption' in msg:
            text = msg['caption']
        else:
            return False
        return ('@' + MY_NAME.lower() in text.lower() or
                text.lower().startswith(MY_COMMAND))

    @staticmethod
    def ellipsis(text, max_):
        return text[:max_ - 3] + '...' if len(text) > max_ else text

    @staticmethod
    def _get_command(text):
        command, _, rest = text.partition(' ')
        command = command[1:]
        rest = rest.strip()
        return command, rest


def compose(filename):
    def clamp(n, minn, maxn):
        ret = max(min(maxn, n), minn)
        print('Clamping %s to %s - %s: %s' % (n, minn, maxn, ret))
        return ret

    with Image(filename=filename) as original:
        bg_img = Image(original)
    # remove the alpha channel, if any
    bg_img.alpha_channel = False

    with Image(filename=MY_MASK) as original:
        mask_img = Image(original)

    mask_w = (bg_img.width / 2) * (bg_img.height / bg_img.width)
    mask_w = clamp(mask_w, bg_img.width / 2.5, bg_img.width / 1.5)
    mask_w = int(mask_w)
    mask_h = bg_img.height
    print('Original %dx%d ratio %.1f' % (bg_img.width, bg_img.height, bg_img.width / bg_img.height))
    mask_img.transform(resize='{}x{}'.format(mask_w, mask_h))

    bg_img.composite(mask_img, left=bg_img.width - mask_w, top=0)

    bg_img.compression_quality = 100
    new_filename = 'tmp/masked_%s.jpg' % (filename.replace('/', '_'))
    bg_img.save(filename=new_filename)
    return new_filename


if __name__ == '__main__':
    bot = TelegramBot(MY_TOKEN)

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
