import logging
import time

from .. import exceptions
from ..entry import StreamPlaylistEntry
from ..utils import write_file
from ..constructs import Response

log = logging.getLogger(__name__)

cog_name = 'autoplaylist'

# @TheerapakG: TODO: bot > self
async def cmd_resetplaylist(self, player, channel):
    """
    Usage:
        {command_prefix}resetplaylist

    Resets all songs in the server's autoplaylist and autostream with no randomization
    """
    if not player.autoplaylist_mode:
        player.auto_mode = dict()
        player.auto_mode['mode'] = self.config.auto_playlist
        if(player.auto_mode['mode'] == 'toggle'):
            player.auto_mode['auto_toggle'] = self.playlisttype[0]
        await self.serialize_json(player.auto_mode, player.voice_client.channel.guild, dir = 'data/%s/mode.json')

    player.autoplaylist = list()
    if self.config.auto_playlist:
        if not self.autoplaylist:
            # TODO: When I add playlist expansion, make sure that's not happening during this check
            log.warning("No playable songs in the autoplaylist, disabling.")
            self.config.auto_playlist = False
            if player.auto_mode['auto_toggle'] == 'playlist' and len(self.playlisttype) > 1:
                try:
                    i = self.playlisttype.index(player.auto_mode['auto_toggle']) + 1
                    if i == len(self.playlisttype):
                        i = 0
                except ValueError:
                    i = 0
                player.auto_mode['auto_toggle'] = self.playlisttype[i]
            await self.serialize_json(player.auto_mode, player.voice_client.channel.guild, dir = 'data/%s/mode.json')
            self.playlisttype.remove('playlist')
        else:
            if player.auto_mode['mode'] == 'merge' or (player.auto_mode['mode'] == 'toggle' and player.auto_mode['auto_toggle'] == 'playlist'):
                log.debug("resetting current autoplaylist...")
                player.autoplaylist.extend([(url, "default") for url in list(self.autoplaylist)])
    if self.config.auto_stream:
        if not self.autostream:
            log.warning("No playable songs in the autostream, disabling.")
            self.config.auto_stream = False
            if player.auto_mode['auto_toggle'] == 'stream' and len(self.playlisttype) > 1:
                try:
                    i = self.playlisttype.index(player.auto_mode['auto_toggle']) + 1
                    if i == len(self.playlisttype):
                        i = 0
                except ValueError:
                    i = 0
                player.auto_mode['auto_toggle'] = self.playlisttype[i]
            await self.serialize_json(player.auto_mode, player.voice_client.channel.guild, dir = 'data/%s/mode.json')
            self.playlisttype.remove('stream')
        else:
            if  player.auto_mode['mode'] == 'merge' or (player.auto_mode['mode'] == 'toggle' and player.auto_mode['auto_toggle'] == 'stream'):
                log.debug("resetting current autostream...")
                player.autoplaylist.extend([(url, "stream") for url in list(self.autostream)])
    return Response(self.str.get('cmd-resetplaylist-response', '\N{OK HAND SIGN}'), delete_after=15)

# @TheerapakG: TODO: bot > self
async def cmd_toggleplaylist(self, author, permissions, player, channel):
    """
    Usage:
        {command_prefix}toggleplaylist

    Toggle between autoplaylist and autostream
    """
    if not player.auto_mode:
        player.auto_mode = dict()
        player.auto_mode['mode'] = self.config.auto_mode
        if(player.auto_mode['mode'] == 'toggle'):
            player.auto_mode['auto_toggle'] = self.playlisttype[0]
        await self.serialize_json(player.auto_mode, player.voice_client.channel.guild, dir = 'data/%s/mode.json')

    if player.auto_mode['mode'] == 'toggle':
        if not permissions.toggle_playlists:
            raise exceptions.PermissionsError(
                self.str.get('cmd-toggleplaylist-noperm', 'You have no permission to toggle autoplaylist'),
                expire_in=30
            )

        if len(self.playlisttype) == 0:
            return Response(self.str.get('cmd-toggleplaylist-nolist', 'There is not any autoplaylist to toggle to'), delete_after=15)
        try:
            i = self.playlisttype.index(player.auto_mode['auto_toggle']) + 1
            if i == len(self.playlisttype):
                i = 0
        except ValueError:
            i = 0
        if self.playlisttype[i] == player.auto_mode['auto_toggle']:
            return Response(self.str.get('cmd-toggleplaylist-nolist', 'There is not any autoplaylist to toggle to'), delete_after=15)
        else:
            player.auto_mode['auto_toggle'] = self.playlisttype[i]
            await self.serialize_json(player.auto_mode, player.voice_client.channel.guild, dir = 'data/%s/mode.json')
            # reset playlist
            player.autoplaylist = list()
            # if autoing then switch
            if player.auto_state.current_value and not player.is_stopped:
                player.skip()
            # on_player_finished_playing should fill in the music
            # done!
            return Response(self.str.get('cmd-toggleplaylist-success', 'Switched autoplaylist to {0}').format(player.auto_mode['auto_toggle']), delete_after=15)
    else:
        return Response(self.str.get('cmd-toggleplaylist-wrongmode', 'Mode for dealing with autoplaylists is not set to \'toggle\', currently set to {0}').format(self.config.auto_mode), delete_after=15)

# @TheerapakG: TODO: bot > self
async def cmd_save(self, player, url=None):
    """
    Usage:
        {command_prefix}save [url]

    Saves the specified song or current song if not specified to the autoplaylist.
    """
    if url or (player.current_entry and not isinstance(player.current_entry, StreamPlaylistEntry)):
        if not url:
            url = player.current_entry.url

        if url not in self.autoplaylist:
            self.autoplaylist.append(url)
            write_file(self.config.auto_playlist_file, self.autoplaylist)
            log.debug("Appended {} to autoplaylist".format(url))
            if 'playlist' not in self.playlisttype:
                self.playlisttype.append('playlist')
            return Response(self.str.get('cmd-save-success', 'Added <{0}> to the autoplaylist.').format(url))
        else:
            raise exceptions.CommandError(self.str.get('cmd-save-exists', 'This song is already in the autoplaylist.'))
    else:
        raise exceptions.CommandError(self.str.get('cmd-save-invalid', 'There is no valid song playing.'))

# @TheerapakG: TODO: bot > self
async def cmd_autostream(self, player, option, url=None):
    """
    Usage:
        {command_prefix}autostream [+, -, add, remove] [url]

    Add or remove the specified stream or current stream if not specified to/from the autostream.
    """
    if (player.current_entry and isinstance(player.current_entry, StreamPlaylistEntry)):
        if not url:
            url = player.current_entry.url
    else:
        if not url:
            raise exceptions.CommandError(self.str.get('cmd-autostream-stream-invalid', 'There is no valid stream playing.'))

    if not url:
        raise exceptions.CommandError(self.str.get('cmd-autostream-nourl', '\'Emptiness\' is not a valid URL. Maybe you forget options?'))
        
    
    if option in ['+', 'add']:
        if url not in self.autostream:
            self.autostream.append(url)
            write_file(self.config.auto_stream_file, self.autostream)
            if 'stream' not in self.playlisttype:
                self.playlisttype.append('stream')
            log.debug("Appended {} to autostream".format(url))
            return Response(self.str.get('cmd-addstream-success', 'Added <{0}> to the autostream.').format(url))
        else:
            raise exceptions.CommandError(self.str.get('cmd-addstream-exists', 'This stream is already in the autostream.'))

    elif option in ['-', 'remove']:
        if url not in self.autostream:
            log.debug("URL \"{}\" not in autostream, ignoring".format(url))
            raise exceptions.CommandError(self.str.get('cmd-removestream-notexists', 'This stream is already not in the autostream.'))

        async with self.aiolocks['remove_from_autostream']:
            self.autostream.remove(url)
            log.info("Removing song from session autostream: %s" % url)

            with open(self.config.auto_stream_removed_file, 'a', encoding='utf8') as f:
                f.write(
                    '# Entry removed {ctime}\n'
                    '# Reason: {re}\n'
                    '{url}\n\n{sep}\n\n'.format(
                        ctime=time.ctime(),
                        re='\n#' + ' ' * 10 + 'removed by user', # 10 spaces to line up with # Reason:
                        url=url,
                        sep='#' * 32
                ))

            log.info("Updating autostream")
            write_file(self.config.auto_stream_file, self.autostream)

        return Response(self.str.get('cmd-removestream-success', 'Removed <{0}> from the autostream.').format(url))

    else:
        raise exceptions.CommandError(self.str.get('cmd-autostream-nooption', 'Check your specified option argument. It needs to be +, -, add or remove.'))
