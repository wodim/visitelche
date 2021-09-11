import asyncio
# from pprint import pprint
import os
import random
import time

import telepot
import telepot.aio

from composer import Composer
import messages

MY_NAME = 'visitelchebot'

CMD_VISITELCHE = '/visitelche'
CMD_PESCANOVA = '/pescanova'
CMD_BULO = '/bulo'
CMD_SUPERBULO = '/superbulo'
CMD_ALVISE = '/alvise'
CMD_MEGAALVISE = '/megaalvise'

# image -> image
IMAGE_CMDS = (CMD_VISITELCHE, CMD_BULO, CMD_SUPERBULO, CMD_ALVISE)
# video -> video
VIDEO_CMDS = (CMD_VISITELCHE, CMD_PESCANOVA)
# image -> video
ITOV_CMDS = (CMD_MEGAALVISE,)
# commands that accept a text parameter
TEXT_CMDS = (CMD_ALVISE, CMD_MEGAALVISE)


class TelegramBot(telepot.aio.Bot):
    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)
        self.last_msg_w_media = {}
        self.last_msg_edit = 0

    async def on_chat_message(self, message):
        _, chat_type, chat_id, _, _ = telepot.glance(message, long=True)
        # pprint(message)

        if self.is_media_message(message):
            # store the last message of every chat
            self.last_msg_w_media[chat_id] = message

        mention = self.check_mention(message)
        args = self.get_text_from_message(message)
        if chat_type in self.PRIVATE_CHATS:
            if 'reply_to_message' in message:
                message = message['reply_to_message']
            if self.is_media_message(message):
                if mention:
                    await self.process(message, mention, args)
                else:
                    commands = ' '.join(self.get_possible_commands(message))
                    await self.send_message(message, caption=messages.AWAITING_INPUT + '\n' + commands)
            else:
                # don't reply with something from last_msg_w_media if this is a reply message
                if chat_id in self.last_msg_w_media and 'reply_to_message' not in message:
                    await self.process(self.last_msg_w_media[chat_id], mention, args)
                else:
                    await self.send_message(message, caption=messages.INVALID_COMMAND)
        elif chat_type in self.PUBLIC_CHATS:
            if mention:
                if 'reply_to_message' in message:
                    message = message['reply_to_message']
                if self.is_media_message(message):
                    await self.process(message, mention, args)
                # don't reply with something from last_msg_w_media if this is a reply message
                elif chat_id in self.last_msg_w_media and 'reply_to_message' not in message:
                    await self.process(self.last_msg_w_media[chat_id], mention, args)
                else:
                    await self.send_message(message, caption=messages.INVALID_COMMAND)

    async def process(self, message, type_, args):
        if not self.is_command_appropriate(message, type_):
            await self.send_message(message, caption=messages.INVALID_INPUT)
            return

        # download the base media
        try:
            file_dest, media_type = await self.download_media(message)
        except ValueError as exc:
            await self.send_message(message, caption=str(exc))
            return

        if media_type == 'photo' and type_ not in ITOV_CMDS:
            chat_action = 'upload_photo'
            attachment_type = 'photo'
            error_caption = messages.FAILED_TO_SEND_PICTURE
            wait_msg = None
        else:
            chat_action = 'upload_video'
            attachment_type = 'file'
            error_caption = messages.FAILED_TO_SEND_VIDEO
            wait_msg = await self.send_message(message, caption=messages.COMPOSING_VIDEO)

        composer = Composer(file_dest)
        fun = getattr(composer, 'compose_%s_%s' % (attachment_type, type_[1:]))
        if type_ in TEXT_CMDS:
            text = (' '.join(args.split(' ')[1:])) if args else None
            new_filename = await fun(text,
                                     callback=self.status_callback,
                                     callback_args=(wait_msg,))
        else:
            new_filename = fun()

        try:
            _, _, chat_id, _, msg_id = telepot.glance(message, long=True)
            await self.sendChatAction(chat_id, chat_action)
            self.last_msg_w_media[chat_id] = await self.send_message(message, quote_msg_id=msg_id,
                                                                     type_=attachment_type,
                                                                     filename=new_filename)
        except Exception:
            await self.send_message(message, caption=error_caption)
        finally:
            if wait_msg:
                await self.deleteMessage(telepot.message_identifier(wait_msg))

    async def status_callback(self, wait_msg, current, total):
        if current == total:
            await self.editMessageText(telepot.message_identifier(wait_msg),
                                       '99.%s%%...' % ('9' * random.randint(3, 12)))
            return

        if current > 0 and self.last_msg_edit < time.time() - 2:
            current_pct = current / total * 100
            await self.editMessageText(telepot.message_identifier(wait_msg),
                                       '%.01f%%...' % (current_pct))
            self.last_msg_edit = time.time()

    async def download_media(self, message):
        if 'video' in message or 'animation' in message:
            if 'video' in message:
                message_video = message['video']
            elif 'animation' in message:
                message_video = message['animation']
            if message_video['file_size'] > 20 * 1024 * 1024:
                raise ValueError(messages.VIDEO_TOO_BIG)
            error_message = messages.FAILED_TO_DOWNLOAD_VIDEO

            file_id = message_video['file_id']
            file_dest = 'tmp/%s.mp4' % file_id
            media_type = 'video'
        elif 'photo' in message:
            error_message = messages.FAILED_TO_DOWNLOAD_PICTURE

            file_id = message['photo'][-1]['file_id']
            file_dest = 'tmp/%s.jpg' % file_id
            media_type = 'photo'
        else:
            raise ValueError('trying to download media from a msg with no media')

        if not os.path.exists(file_dest):
            try:
                await self.download_file(file_id, file_dest)
            except:
                raise ValueError(error_message)

        return file_dest, media_type

    @staticmethod
    def is_command_appropriate(message, type_):
        return ('photo' in message and (type_ in IMAGE_CMDS or type_ in ITOV_CMDS or type_ is None) or
                (('video' in message or 'animation' in message) and type_ in VIDEO_CMDS))

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
            return IMAGE_CMDS + ITOV_CMDS
        if TelegramBot.is_video_message(message):
            return VIDEO_CMDS
        return ()

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
    def get_text_from_message(message):
        if 'text' in message:
            return message['text']
        if 'caption' in message:
            return message['caption']
        return None

    @staticmethod
    def check_mention(message):
        if not (text := TelegramBot.get_text_from_message(message)):
            return False
        if ' ' in text:
            text = text.split(' ')[0]
        if text.lower() == '@' + MY_NAME.lower():
            return CMD_VISITELCHE
        for cmd in IMAGE_CMDS + VIDEO_CMDS + ITOV_CMDS:
            if (text.lower() == cmd or
                    text.lower().startswith(cmd + '@' + MY_NAME)):
                return cmd
        return False

    @staticmethod
    def ellipsis(text, max_):
        return text[:max_ - 1] + '…' if len(text) > max_ else text


if __name__ == '__main__':
    bot = TelegramBot(open('token', 'rt').read().strip())

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
