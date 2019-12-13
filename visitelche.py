import asyncio
# from pprint import pprint
import subprocess

from wand.image import Image
import telepot
import telepot.aio


MY_NAME = 'visitelchebot'
MY_COMMANDS = ('/visitelche', '/tiktok')
MY_TOKEN = ''
MY_MASK = 'elche.png'

FFMPEG_CMD = ('ffmpeg -i \'{source}\' -loop 1 -start_number 1 '
              '-start_number_range 8 -i tiktok/%02d.png -filter_complex '
              '"[1:v][0:v]scale2ref=oh*mdar:h=ih/8[logo][base];'
              '[base][logo]overlay=0:0:eof_action=endall[v]" '
              '-map [v] -map 0:a? -y -preset ultrafast \'{dest}\'')

last_msg_w_photo = {}
last_msg_w_video = {}
last_msg_type_was = {}


class TelegramBot(telepot.aio.Bot):
    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)

    async def on_chat_message(self, message):
        content_type, chat_type, chat_id, _, msg_id = telepot.glance(message, long=True)
        # pprint(message)
        original_message = message

        if chat_type in self.PUBLIC_CHATS and 'photo' in message:
            last_msg_w_photo[chat_id] = message
            last_msg_type_was[chat_id] = 'photo'
        if chat_type in self.PUBLIC_CHATS and 'video' in message:
            last_msg_w_video[chat_id] = message
            last_msg_type_was[chat_id] = 'video'

        if chat_type in self.PRIVATE_CHATS:
            if 'reply_to_message' in message:
                message = message['reply_to_message']
            if 'photo' in message:
                await self.process_photo(original_message, message, chat_id)
            elif 'video' in message:
                await self.process_video(original_message, message, chat_id)
            else:
                if self.check_mention(message) and chat_id in last_msg_w_photo:
                    await self.process_photo(original_message, last_msg_w_photo[chat_id], chat_id)
                else:
                    await self.send_message(message, caption='e')
        elif chat_type in self.PUBLIC_CHATS:
            if 'reply_to_message' in message:
                if self.check_mention(message):
                    message = message['reply_to_message']
                    if 'photo' in message:
                        await self.process_photo(original_message, message, chat_id)
                    elif 'video' in message:
                        await self.process_video(original_message, message, chat_id)
                    else:
                        await self.send_message(message, caption='e')
            else:
                if self.check_mention(message):
                    if 'photo' in message:
                        await self.process_photo(original_message, message, chat_id)
                    elif 'video' in message:
                        await self.process_video(original_message, message, chat_id)
                    else:
                        if chat_id in last_msg_type_was:
                            if last_msg_type_was[chat_id] == 'photo':
                                await self.process_photo(original_message, last_msg_w_photo[chat_id], chat_id)
                            elif last_msg_type_was[chat_id] == 'video':
                                await self.process_video(original_message, last_msg_w_video[chat_id], chat_id)
                        else:
                            await self.send_message(message, caption='e')

    async def process_photo(self, original_message, message, chat_id):
        await self.sendChatAction(chat_id, 'upload_photo')
        file_id = message['photo'][-1]['file_id']
        file_dest = 'tmp/%s.jpg' % file_id
        print('Downloading')
        try:
            await self.download_file(file_id, file_dest)
        except:
            await self.send_message(message, caption='no me he podido bajar la foto :(')
        print('Downloaded. Composing')
        new_filename = compose(file_dest)
        print('Composed. Sending')
        try:
            msg_id = telepot.message_identifier(original_message)
            last_msg_w_photo[chat_id] = await self.send_message(original_message, quote_msg_id=msg_id,
                                                                type='photo', filename=new_filename)
        except:
            await self.send_message(message, caption='no he podido enviar la foto tuneada :(')
        print('Sent')

    async def process_video(self, original_message, message, chat_id):
        if message['video']['file_size'] > 20 * 1024 * 1024:
            await self.send_message(message, caption='un poco grande no hijo de puta?')
        wait_msg = await self.send_message(message, caption=('vale, recibido. no me atosigues porque soy '
                                                             'un pobre procesador arm de 3€ al mes'))
        file_id = message['video']['file_id']
        file_dest = 'tmp/%s.mp4' % file_id
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
        print('Composed. Sending')
        await self.sendChatAction(chat_id, 'upload_video')
        try:
            msg_id = telepot.message_identifier(original_message)
            last_msg_w_video[chat_id] = await self.send_message(original_message, quote_msg_id=msg_id,
                                                                type='file', filename=new_filename)
            await self.deleteMessage(telepot.message_identifier(wait_msg))
        except:
            await self.send_message(message, caption='no he podido enviar el vídeo tuneado :(')
        print('Sent')

    async def send_message(self, message, caption=None, filename=None,
                           type='text', no_preview=False,
                           quote_msg_id=None):
        """helper function to send messages to users."""
        if type == 'text':
            if not caption:
                raise ValueError('You need a caption parameter to send text')
            text = self.ellipsis(caption, 4096)
            return await self.sendMessage(message['chat']['id'], text,
                                          disable_web_page_preview=no_preview,
                                          reply_to_message_id=quote_msg_id)
        elif type == 'photo':
            if not filename:
                raise ValueError('You need a file parameter to send a photo')
            if caption:
                caption = self.ellipsis(caption, 200)
            with open(filename, 'rb') as f:
                return await self.sendPhoto(message['chat']['id'], f, caption=caption,
                                            reply_to_message_id=quote_msg_id)
        elif type == 'file':
            if not filename:
                raise ValueError('You need a file parameter to send a file')
            if caption:
                raise ValueError("You can't send a caption with a file")
            with open(filename, 'rb') as f:
                return await self.sendDocument(message['chat']['id'], f,
                                               reply_to_message_id=quote_msg_id)

    def check_mention(self, msg):
        if 'text' in msg:
            text = msg['text']
        elif 'caption' in msg:
            text = msg['caption']
        else:
            return False
        if '@' + MY_NAME.lower() in text.lower():
            return True
        for command in MY_COMMANDS:
            if text.lower().startswith(command):
                return True
        return False

    @staticmethod
    def ellipsis(text, max):
        return text[:max - 3] + '...' if len(text) > max else text

    @staticmethod
    def _get_command(text):
        command, _, rest = text.partition(' ')
        command = command[1:]
        rest = rest.strip()
        return command, rest

    @staticmethod
    def format_name(message):
        """formats a "from" property into a string"""
        if 'from' not in message:
            return None
        longname = []
        if 'username' in message['from']:
            longname.append('@' + message['from']['username'])
        if 'first_name' in message['from']:
            longname.append(message['from']['first_name'])
        if 'last_name' in message['from']:
            longname.append(message['from']['last_name'])
        return ', '.join(longname)


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
