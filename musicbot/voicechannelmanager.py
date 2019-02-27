from discord import VoiceChannel, Member
from .player import MusicPlayer
from .playlist import Playlist
from .constructs import SkipState
from .messagemanager import safe_delete_message, safe_edit_message, safe_send_message
from . import downloader
from . import exceptions
from .utils import _func_
from .guildmanager import ManagedGuild
from collections import defaultdict
import logging
import random
import asyncio

log = logging.getLogger(__name__)

class ManagedVC:
    def __init__(self, guild: ManagedGuild, vc: VoiceChannel):
        self._aiolocks = defaultdict(asyncio.Lock)
        self._guild = guild
        self._vc = vc
        self._player = None
        guild._player_channel = self

    def __str__(self):
        return self._vc.name

    def __repr__(self):
        return '<ManagedVC voicechannel={vc} guild={guild} player={player}>'.format(
            vc=repr(self._vc),
            guild=repr(self._guild),
            player=repr(self._player)
            )

    def _init_player(self, player: MusicPlayer):
        player = player.on('play', self.on_player_play) \
                       .on('resume', self.on_player_resume) \
                       .on('pause', self.on_player_pause) \
                       .on('stop', self.on_player_stop) \
                       .on('finished-playing', self.on_player_finished_playing) \
                       .on('entry-added', self.on_player_entry_added) \
                       .on('error', self.on_player_error)

        player.skip_state = SkipState()

        self._player = player

        return player

    async def kill_player(self):
        self._player.kill()

    async def move_channel(self, channel: VoiceChannel):
        voice_client = self._guild.voice_client_in()
        if voice_client and self._guild._guild == channel.guild:
            self._vc = channel
            await voice_client.move_to(channel)

    async def get_player(self, *, create=False, deserialize=False) -> MusicPlayer:

        async with self._aiolocks[_func_()]:
            if deserialize:
                voice_client = await self._guild.get_voice_client()
                player = await self._guild.deserialize_queue(voice_client)

                if player:
                    log.debug("Created player via deserialization for guild %s with %s entries", self._guild._guildid, len(player.playlist))
                    # Since deserializing only happens when the bot starts, I should never need to reconnect
                    return self._init_player(player)

            if not self._player:
                if not create:
                    raise exceptions.CommandError(
                        'The bot is not in a voice channel.  '
                        'Use %ssummon to summon it to your voice channel.' % self._guild._client.config.command_prefix)

                voice_client = await self._guild.get_voice_client()

                playlist = Playlist(self)
                player = MusicPlayer(self, voice_client, playlist)
                self._init_player(player)

        return self._player

    async def on_player_play(self, player: MusicPlayer, entry):
        log.debug('Running on_player_play')
        await self._guild._client.update_now_playing_status(entry)
        player.skip_state.reset()

        # This is the one event where its ok to serialize autoplaylist entries
        await self._guild.serialize_queue()

        if self._guild._client.config.write_current_song:
            await self._guild.write_current_song(entry)

        channel = entry.meta.get('channel', None)
        author = entry.meta.get('author', None)

        if channel and author:
            last_np_msg = self._guild._data['last_np_msg']
            if last_np_msg and last_np_msg.channel == channel:

                async for lmsg in channel.history(limit=1):
                    if lmsg != last_np_msg and last_np_msg:
                        await safe_delete_message(last_np_msg)
                        self._guild._data['last_np_msg'] = None
                    break  # This is probably redundant

            author_perms = self._guild._client.permissions.for_user(author)

            if author not in player.voice_client.channel.members and author_perms.skip_when_absent:
                newmsg = 'Skipping next song in `%s`: `%s` added by `%s` as queuer not in voice' % (
                    player.voice_client.channel.name, entry.title, entry.meta['author'].name)
                player.skip()
            elif self._guild._client.config.now_playing_mentions:
                newmsg = '%s - your song `%s` is now playing in `%s`!' % (
                    entry.meta['author'].mention, entry.title, player.voice_client.channel.name)
            else:
                newmsg = 'Now playing in `%s`: `%s` added by `%s`' % (
                    player.voice_client.channel.name, entry.title, entry.meta['author'].name)

            if self._guild._data['last_np_msg']:
                self._guild._data['last_np_msg'] = await safe_edit_message(last_np_msg, newmsg, send_if_fail=True)
            else:
                self._guild._data['last_np_msg'] = await safe_send_message(channel, newmsg)

        # TODO: Check channel voice state?

    async def on_player_resume(self, player: MusicPlayer, entry, **_):
        log.debug('Running on_player_resume')
        await self._guild._client.update_now_playing_status(entry)

    async def on_player_pause(self, player: MusicPlayer, entry, **_):
        log.debug('Running on_player_pause')
        await self._guild._client.update_now_playing_status(entry, True)
        # await self._guild.serialize_queue()

    async def on_player_stop(self, player: MusicPlayer, **_):
        log.debug('Running on_player_stop')
        await self._guild._client.update_now_playing_status()

    async def on_player_finished_playing(self, player: MusicPlayer, **_):
        log.debug('Running on_player_finished_playing')
        def _autopause(player):
            if self._guild._client._check_if_empty(player.voice_client.channel):
                log.info("Player finished playing, autopaused in empty channel")

                player.pause()
                self._guild._data['auto_paused'] = True

        if not player.playlist.entries and not player.current_entry and self._guild._client.config.auto_playlist:
            if not player.autoplaylist:
                if not self._guild._client.autoplaylist:
                    # TODO: When I add playlist expansion, make sure that's not happening during this check
                    log.warning("No playable songs in the autoplaylist, disabling.")
                    self._guild._client.config.auto_playlist = False
                else:
                    log.debug("No content in current autoplaylist. Filling with new music...")
                    player.autoplaylist = list(self._guild._client.autoplaylist)

            while player.autoplaylist:
                if self._guild._client.config.auto_playlist_random:
                    random.shuffle(player.autoplaylist)
                    song_url = random.choice(player.autoplaylist)
                else:
                    song_url = player.autoplaylist[0]
                player.autoplaylist.remove(song_url)

                info = {}

                try:
                    info = await self._guild._client.downloader.extract_info(player.playlist.loop, song_url, download=False, process=False)
                except downloader.youtube_dl.utils.DownloadError as e:
                    if 'YouTube said:' in e.args[0]:
                        # url is bork, remove from list and put in removed list
                        log.error("Error processing youtube url:\n{}".format(e.args[0]))

                    else:
                        # Probably an error from a different extractor, but I've only seen youtube's
                        log.error("Error processing \"{url}\": {ex}".format(url=song_url, ex=e))

                    await self._guild._client.remove_from_autoplaylist(song_url, ex=e, delete_from_ap=self._guild._client.config.remove_ap)
                    continue

                except Exception as e:
                    log.error("Error processing \"{url}\": {ex}".format(url=song_url, ex=e))
                    log.exception()

                    self._guild._client.autoplaylist.remove(song_url)
                    continue

                if info.get('entries', None):  # or .get('_type', '') == 'playlist'
                    log.debug("Playlist found but is unsupported at this time, skipping.")
                    # TODO: Playlist expansion

                # Do I check the initial conditions again?
                # not (not player.playlist.entries and not player.current_entry and self.config.auto_playlist)

                if self._guild._client.config.auto_pause:
                    player.once('play', lambda player, **_: _autopause(player))

                try:
                    await player.playlist.add_entry(song_url, channel=None, author=None)
                except exceptions.ExtractionError as e:
                    log.error("Error adding song from autoplaylist: {}".format(e))
                    log.debug('', exc_info=True)
                    continue

                break

            if not self._guild._client.autoplaylist:
                # TODO: When I add playlist expansion, make sure that's not happening during this check
                log.warning("No playable songs in the autoplaylist, disabling.")
                self._guild._client.config.auto_playlist = False

        else: # Don't serialize for autoplaylist events
            await self._guild.serialize_queue()

        if not player.is_stopped and not player.is_dead:
            player.play(_continue=True)

    async def on_player_entry_added(self, player: MusicPlayer, playlist, entry, **_):
        log.debug('Running on_player_entry_added')
        if entry.meta.get('author') and entry.meta.get('channel'):
            await self._guild.serialize_queue()

    async def on_player_error(self, player: MusicPlayer, entry, ex, **_):
        if 'channel' in entry.meta:
            await safe_send_message(
                entry.meta['channel'],
                "```\nError from FFmpeg:\n{}\n```".format(ex)
            )
        else:
            log.exception("Player error", exc_info=ex)

    def is_empty(self, exclude_me = True, exclude_deaf = False):
        def check(member: Member):
            if exclude_me and member == self._vc.guild.me:
                return False

            if exclude_deaf and any([member.voice.deaf, member.voice.self_deaf]):
                return False

            return True

        return not sum(1 for m in self._vc.members if check(m))

    async def disconnect_voice_client(self):
        v = await self._guild.get_voice_client(create=False)
        if not v:
            return
        log.debug('disconnecting voice client in {}'.format(self._guild._guild.name))
        if self._player:
            self._player.kill()
        await v.disconnect()
        

    async def set_voice_state(self, *, mute=False, deaf=False):
        await self._vc.ws.voice_state(self._vc.guild.id, self._vc.id, mute, deaf)
        # I hope I don't have to set the channel here
        # instead of waiting for the event to update it

