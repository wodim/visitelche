import asyncio
# from pprint import pprint
import os
import random
import subprocess

from wand.image import Image
import telepot
import telepot.aio


MY_NAME = 'visitelchebot'

MY_COMMAND = '/visitelche'
MY_COMMAND_P = '/pescanova'
MY_COMMAND_B = '/bulo'

IMAGE_CMDS = (MY_COMMAND, MY_COMMAND_B)
VIDEO_CMDS = (MY_COMMAND, MY_COMMAND_P)

MASKS = {
    MY_COMMAND: ('assets/elche.png',),
    MY_COMMAND_B: ('assets/bulo1.png', 'assets/bulo2.png', 'assets/bulo3.png',),
}

FFMPEG_CMD = ('ffmpeg -hide_banner '
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
              '\'{dest}\'')

FFMPEG_CMP = ('ffmpeg -hide_banner '
              # first input: base video
              '-i \'{source}\' '
              # second input: base audio
              '-i assets/pescanova.aac '
              # output options
              ' -map 0:0 -map 1:0 -c:a copy -c:v copy -shortest -y '
              '\'{dest}\'')


class TelegramBot(telepot.aio.Bot):
    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)
        self.last_msg_w_media = {}

    async def on_chat_message(self, message):
        _, chat_type, chat_id, _, _ = telepot.glance(message, long=True)
        # pprint(message)

        if self.is_media_message(message):
            # store the last message of every chat
            self.last_msg_w_media[chat_id] = message

        if chat_type in self.PRIVATE_CHATS:
            mention = self.check_mention(message)
            if 'reply_to_message' in message:
                message = message['reply_to_message']
            if self.is_media_message(message):
                if mention:
                    await self.process(message, mention)
                else:
                    commands = ' '.join(self.get_possible_commands(message))
                    await self.send_message(message, caption='me lo guardo, dime qué hago:\n' + commands)
            else:
                # don't reply with something from last_msg_w_media if this is a reply message
                if chat_id in self.last_msg_w_media and 'reply_to_message' not in message:
                    await self.process(self.last_msg_w_media[chat_id], mention)
                else:
                    await self.send_message(message, caption='e')
        elif chat_type in self.PUBLIC_CHATS:
            mention = self.check_mention(message)
            if mention:
                if 'reply_to_message' in message:
                    message = message['reply_to_message']
                if self.is_media_message(message):
                    await self.process(message, mention)
                # don't reply with something from last_msg_w_media if this is a reply message
                elif chat_id in self.last_msg_w_media and 'reply_to_message' not in message:
                    await self.process(self.last_msg_w_media[chat_id], mention)
                else:
                    await self.send_message(message, caption='e')

    async def process(self, message, type_=None):
        if 'photo' in message and (type_ in IMAGE_CMDS or type_ is None):
            await self.process_image(message, type_)
        elif ('video' in message or 'animation' in message) and type_ in VIDEO_CMDS:
            await self.process_video(message, type_)
        else:
            await self.send_message(message, caption='mis kojones')

    @staticmethod
    def is_media_message(message):
        return TelegramBot.is_photo_message(message) or TelegramBot.is_video_message(message)

    @staticmethod
    def is_photo_message(message):
        return 'photo' in message

    @staticmethod
    def is_video_message(message):
        return 'video' in message or 'animation' in message

    @staticmethod
    def get_possible_commands(message):
        if TelegramBot.is_photo_message(message):
            return IMAGE_CMDS
        elif TelegramBot.is_video_message(message):
            return VIDEO_CMDS
        else:
            return ()

    async def process_image(self, message, type_):
        file_id = message['photo'][-1]['file_id']
        file_dest = 'tmp/%s.jpg' % file_id
        if not os.path.exists(file_dest):
            print('Downloading')
            try:
                await self.download_file(file_id, file_dest)
            except:
                await self.send_message(message, caption='no me he podido bajar la foto :(')
        print('Downloaded. Composing')
        new_filename = compose(file_dest, type_)
        print('Composed. Sending')
        try:
            _, _, chat_id, _, msg_id = telepot.glance(message, long=True)
            await self.sendChatAction(chat_id, 'upload_photo')
            self.last_msg_w_media[chat_id] = await self.send_message(message, quote_msg_id=msg_id,
                                                                     type_='photo', filename=new_filename)
        except:
            await self.send_message(message, caption='no he podido enviar la foto tuneada :(')
        print('Sent')

    async def process_video(self, message, type_):
        if 'video' in message:
            message_video = message['video']
        elif 'animation' in message:
            message_video = message['animation']
        if message_video['file_size'] > 20 * 1024 * 1024:
            await self.send_message(message, caption='un poco grande no hijo de puta?')
            return
        wait_msg = await self.send_message(message, caption=('vale, recibido. no me atosigues porque soy '
                                                             'un pobre procesador arm de 3€ al mes'))
        file_id = message_video['file_id']
        file_dest = 'tmp/%s.mp4' % file_id
        if not os.path.exists(file_dest):
            print('Downloading')
            try:
                await self.download_file(file_id, file_dest)
            except Exception as exc:
                await self.send_message(message, caption='no me he podido bajar el vídeo :(')
                print('Failed to download video. Error was: ' + str(exc))
                return
        print('Downloaded. Composing')
        new_filename = 'tmp/%s_.mp4' % file_id
        if type_ == MY_COMMAND_P:
            cmd = FFMPEG_CMP.format(source=file_dest, dest=new_filename)
        else:
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
            self.last_msg_w_media[chat_id] = await self.send_message(message, quote_msg_id=msg_id,
                                                                     type_='file', filename=new_filename)
        except Exception as exc:
            await self.send_message(message, caption='no he podido enviar el vídeo tuneado :(')
            print('Failed to send video. Error was: ' + str(exc))
            return
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
        if type_ == 'photo':
            if not filename:
                raise ValueError('You need a file parameter to send a photo')
            if caption:
                caption = self.ellipsis(caption, 200)
            with open(filename, 'rb') as f:
                return await self.sendPhoto(message['chat']['id'], f, caption=caption,
                                            reply_to_message_id=quote_msg_id)
        if type_ == 'file':
            if not filename:
                raise ValueError('You need a file parameter to send a file')
            if caption:
                raise ValueError("You can't send a caption with a file")
            with open(filename, 'rb') as f:
                return await self.sendDocument(message['chat']['id'], f,
                                               reply_to_message_id=quote_msg_id)
        raise ValueError('Unknown message type ' + type_)

    @staticmethod
    def check_mention(msg):
        if 'text' in msg:
            text = msg['text']
        elif 'caption' in msg:
            text = msg['caption']
        else:
            return False
        if text.lower() == '@' + MY_NAME.lower():
            return MY_COMMAND
        for cmd in IMAGE_CMDS + VIDEO_CMDS:
            if (text.lower() == cmd or
                    text.lower().startswith(cmd + '@' + MY_NAME)):
                return cmd

    @staticmethod
    def ellipsis(text, max_):
        return text[:max_ - 3] + '...' if len(text) > max_ else text


def compose(filename, type_):
    def clamp(number, minn, maxn):
        return max(min(maxn, number), minn)

    if type_ not in IMAGE_CMDS:
        raise ValueError('incorrect type for compose %s' % type_)

    with Image(filename=filename) as original:
        bg_img = Image(original)
    # remove the alpha channel, if any
    bg_img.alpha_channel = False

    with Image(filename=random.choice(MASKS[type_])) as original:
        mask_img = Image(original)

    if type_ == MY_COMMAND:
        mask_w = (bg_img.width / 2) * (bg_img.height / bg_img.width)
        mask_w = clamp(mask_w, bg_img.width / 2.5, bg_img.width / 1.5)
        mask_w = int(mask_w)
        mask_h = bg_img.height
        mask_img.transform(resize='%dx%d' % (mask_w, mask_h))
        bg_img.composite(mask_img, left=bg_img.width - mask_w, top=0)
    elif type_ == MY_COMMAND_B:
        mask_img.transform(resize='%dx%d' % (bg_img.width, bg_img.height))
        bg_img.composite(mask_img, gravity='center')

    bg_img.compression_quality = 100
    new_filename = 'tmp/masked_%s.jpg' % (filename.replace('/', '_'))
    bg_img.save(filename=new_filename)
    return new_filename


if __name__ == '__main__':
    bot = TelegramBot(open('token', 'rt').read().strip())

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
