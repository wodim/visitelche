import asyncio
from pprint import pprint

from wand.image import Image
import telepot
import telepot.aio


MY_NAME = 'visitelchebot'
MY_COMMAND = '/visitelche'
MY_TOKEN = ''
MY_MASK = 'elche.png'

last_msg_w_photo = {}


class TelegramBot(telepot.aio.Bot):
    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)

    async def on_chat_message(self, message):
        content_type, chat_type, chat_id, _, msg_id = telepot.glance(message, long=True)
        #pprint(message)
        original_message = message

        if chat_type in self.PUBLIC_CHATS and 'photo' in message:
            last_msg_w_photo[chat_id] = message

        if chat_type in self.PRIVATE_CHATS:
            if 'reply_to_message' in message:
                message = message['reply_to_message']
            if 'photo' not in message:
                if self.check_mention(message) and chat_id in last_msg_w_photo:
                    message = last_msg_w_photo[chat_id]
                else:
                    await self.send_message(message, caption='e')
                    return
        elif chat_type in self.PUBLIC_CHATS:
            if 'reply_to_message' in message:
                if self.check_mention(message):
                    message = message['reply_to_message']
                    if 'photo' not in message:
                        await self.send_message(message, caption='e')
                        return
                else:
                    return
            else:
                if self.check_mention(message):
                    if 'photo' not in message:
                        if chat_id in last_msg_w_photo:
                            message = last_msg_w_photo[chat_id]
                        else:
                            await self.send_message(message, caption='e')
                            return
                else:
                    return

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
            last_msg_w_photo[chat_id] = await self.send_message(original_message, quote_msg_id=msg_id,
                                                                type='photo', filename=new_filename)
        except:
            await self.send_message(message, caption='no he podido enviar la foto tuneada :(')
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
        return ('@' + MY_NAME.lower() in text.lower() or
                text.lower().startswith(MY_COMMAND))

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
