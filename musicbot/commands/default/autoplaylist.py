import logging
import time

from ... import exceptions
from ...entry import StreamPlaylistEntry
from ...utils import write_file
from ...constructs import Response

from ... import guildmanager
from ... import voicechannelmanager
from ... import messagemanager

log = logging.getLogger(__name__)

cog_name = 'autoplaylist'

async def cmd_resetplaylist(bot, guild, player, channel):
    """
    Usage:
        {command_prefix}resetplaylist

    Resets all songs in the server's autoplaylist and autostream with no randomization
    """
    mguild = guildmanager.get_guild(bot, guild)

    if not player.autoplaylist_mode:
        player.auto_mode = dict()
        player.auto_mode['mode'] = bot.config.auto_playlist
        if(player.auto_mode['mode'] == 'toggle'):
            player.auto_mode['auto_toggle'] = bot.playlisttype[0]
        await mguild.serialize_json(player.auto_mode, dir = 'data/%s/mode.json')

    player.autoplaylist = list()
    if bot.config.auto_playlist:
        if not bot.autoplaylist:
            # TODO: When I add playlist expansion, make sure that's not happening during this check
            log.warning("No playable songs in the autoplaylist, disabling.")
            bot.config.auto_playlist = False
            if player.auto_mode['auto_toggle'] == 'playlist' and len(bot.playlisttype) > 1:
                try:
                    i = bot.playlisttype.index(player.auto_mode['auto_toggle']) + 1
                    if i == len(bot.playlisttype):
                        i = 0
                except ValueError:
                    i = 0
                player.auto_mode['auto_toggle'] = bot.playlisttype[i]
            await mguild.serialize_json(player.auto_mode, dir = 'data/%s/mode.json')
            bot.playlisttype.remove('playlist')
        else:
            if player.auto_mode['mode'] == 'merge' or (player.auto_mode['mode'] == 'toggle' and player.auto_mode['auto_toggle'] == 'playlist'):
                log.debug("resetting current autoplaylist...")
                player.autoplaylist.extend([(url, "default") for url in list(bot.autoplaylist)])
    if bot.config.auto_stream:
        if not bot.autostream:
            log.warning("No playable songs in the autostream, disabling.")
            bot.config.auto_stream = False
            if player.auto_mode['auto_toggle'] == 'stream' and len(bot.playlisttype) > 1:
                try:
                    i = bot.playlisttype.index(player.auto_mode['auto_toggle']) + 1
                    if i == len(bot.playlisttype):
                        i = 0
                except ValueError:
                    i = 0
                player.auto_mode['auto_toggle'] = bot.playlisttype[i]
            await mguild.serialize_json(player.auto_mode, dir = 'data/%s/mode.json')
            bot.playlisttype.remove('stream')
        else:
            if  player.auto_mode['mode'] == 'merge' or (player.auto_mode['mode'] == 'toggle' and player.auto_mode['auto_toggle'] == 'stream'):
                log.debug("resetting current autostream...")
                player.autoplaylist.extend([(url, "stream") for url in list(bot.autostream)])
    return Response(bot.str.get('cmd-resetplaylist-response', '\N{OK HAND SIGN}'), delete_after=15)

async def cmd_toggleplaylist(bot, author, permissions, guild, player, channel):
    """
    Usage:
        {command_prefix}toggleplaylist

    Toggle between autoplaylist and autostream
    """
    mguild = guildmanager.get_guild(bot, guild)

    if not player.auto_mode:
        player.auto_mode = dict()
        player.auto_mode['mode'] = bot.config.auto_mode
        if(player.auto_mode['mode'] == 'toggle'):
            player.auto_mode['auto_toggle'] = bot.playlisttype[0]
        await mguild.serialize_json(player.auto_mode, dir = 'data/%s/mode.json')

    if player.auto_mode['mode'] == 'toggle':
        if not permissions.toggle_playlists:
            raise exceptions.PermissionsError(
                bot.str.get('cmd-toggleplaylist-noperm', 'You have no permission to toggle autoplaylist'),
                expire_in=30
            )

        if len(bot.playlisttype) == 0:
            return Response(bot.str.get('cmd-toggleplaylist-nolist', 'There is not any autoplaylist to toggle to'), delete_after=15)
        try:
            i = bot.playlisttype.index(player.auto_mode['auto_toggle']) + 1
            if i == len(bot.playlisttype):
                i = 0
        except ValueError:
            i = 0
        if bot.playlisttype[i] == player.auto_mode['auto_toggle']:
            return Response(bot.str.get('cmd-toggleplaylist-nolist', 'There is not any autoplaylist to toggle to'), delete_after=15)
        else:
            player.auto_mode['auto_toggle'] = bot.playlisttype[i]
            await mguild.serialize_json(player.auto_mode, dir = 'data/%s/mode.json')
            # reset playlist
            player.autoplaylist = list()
            # if autoing then switch
            if player.auto_state.current_value and not player.is_stopped:
                player.skip()
            # on_player_finished_playing should fill in the music
            # done!
            return Response(bot.str.get('cmd-toggleplaylist-success', 'Switched autoplaylist to {0}').format(player.auto_mode['auto_toggle']), delete_after=15)
    else:
        return Response(bot.str.get('cmd-toggleplaylist-wrongmode', 'Mode for dealing with autoplaylists is not set to \'toggle\', currently set to {0}').format(bot.config.auto_mode), delete_after=15)

async def cmd_save(bot, player, url=None):
    """
    Usage:
        {command_prefix}save [url]

    Saves the specified song or current song if not specified to the autoplaylist.
    """
    if url or (player.current_entry and not isinstance(player.current_entry, StreamPlaylistEntry)):
        if not url:
            url = player.current_entry.url

        if url not in bot.autoplaylist:
            bot.autoplaylist.append(url)
            write_file(bot.config.auto_playlist_file, bot.autoplaylist)
            log.debug("Appended {} to autoplaylist".format(url))
            if 'playlist' not in bot.playlisttype:
                bot.playlisttype.append('playlist')
            return Response(bot.str.get('cmd-save-success', 'Added <{0}> to the autoplaylist.').format(url))
        else:
            raise exceptions.CommandError(bot.str.get('cmd-save-exists', 'This song is already in the autoplaylist.'))
    else:
        raise exceptions.CommandError(bot.str.get('cmd-save-invalid', 'There is no valid song playing.'))

async def cmd_autostream(bot, player, option, url=None):
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
            raise exceptions.CommandError(bot.str.get('cmd-autostream-stream-invalid', 'There is no valid stream playing.'))

    if not url:
        raise exceptions.CommandError(bot.str.get('cmd-autostream-nourl', '\'Emptiness\' is not a valid URL. Maybe you forget options?'))
        
    
    if option in ['+', 'add']:
        if url not in bot.autostream:
            bot.autostream.append(url)
            write_file(bot.config.auto_stream_file, bot.autostream)
            if 'stream' not in bot.playlisttype:
                bot.playlisttype.append('stream')
            log.debug("Appended {} to autostream".format(url))
            return Response(bot.str.get('cmd-addstream-success', 'Added <{0}> to the autostream.').format(url))
        else:
            raise exceptions.CommandError(bot.str.get('cmd-addstream-exists', 'This stream is already in the autostream.'))

    elif option in ['-', 'remove']:
        if url not in bot.autostream:
            log.debug("URL \"{}\" not in autostream, ignoring".format(url))
            raise exceptions.CommandError(bot.str.get('cmd-removestream-notexists', 'This stream is already not in the autostream.'))

        async with bot.aiolocks['remove_from_autostream']:
            bot.autostream.remove(url)
            log.info("Removing song from session autostream: %s" % url)

            with open(bot.config.auto_stream_removed_file, 'a', encoding='utf8') as f:
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
            write_file(bot.config.auto_stream_file, bot.autostream)

        return Response(bot.str.get('cmd-removestream-success', 'Removed <{0}> from the autostream.').format(url))

    else:
        raise exceptions.CommandError(bot.str.get('cmd-autostream-nooption', 'Check your specified option argument. It needs to be +, -, add or remove.'))
