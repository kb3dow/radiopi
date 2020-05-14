''' try an app settings class '''
import json


class AppConfig:
    ''' Class to hold settings for the app '''
    __config_file = 'radiopi.json'
    __conf = {
    }
    __setters = ["rpi_player:volume",
                 "rpi_player:track",
                 "rpi_player:lcdcolor",
                 "rpi_player:playlist",
                 ]

    @staticmethod
    def config_save():
        ''' save settings to json file '''
        with open(AppConfig.__config_file, "w") as conf_file:
            json.dump(AppConfig.__conf, conf_file, indent=4)

    @staticmethod
    def config_load():
        ''' load settings from json file '''
        with open(AppConfig.__config_file, "r") as conf_file:
            AppConfig.__conf = json.load(conf_file)

    @staticmethod
    def get(name, section=None):
        ''' get the value of a setting from a given section '''
        if section:
            if section in AppConfig.__conf:
                if name in AppConfig.__conf[section]:
                    ret = AppConfig.__conf[section][name]
                else:
                    raise NameError("No name: %s in section name: %s"
                                    % (name, section))
            else:
                raise NameError("No section: %s" % (section))
        else:
            if name in AppConfig.__conf:
                ret = AppConfig.__conf[name]
            else:
                raise NameError("No variable: %s" % (name))
        return ret

    @staticmethod
    def set(value, name, section=None):
        ''' set the value of a setting in a given section '''
        if section + ':' + name in AppConfig.__setters:
            if section:
                AppConfig.__conf[section][name] = value
            else:
                AppConfig.__conf[name] = value
        else:
            raise NameError("%s: not accepted in set() method"
                            % (section + ':' + name))


'''
settings = {
    'rpi_player': {
        'volume': 24,
        'track': 6,
        'lcdcolor': 4,
        'playlist': 'Carnatic'
    },

    'mpdclient': {
        'port': 6600,
        'timeout': 3600,
        'host': 'localhost'
    }
}

# Writing to sample.json
with open("settings.json", "w") as f:
    json.dump(settings, f, indent=4)

print(settings)
'''

if __name__ == "__main__":
    # from config import AppConfig
    AppConfig.config_load()
    print('volume:', AppConfig.get('volume', 'rpi_player'))
    AppConfig.set(33, 'volume', 'rpi_player')
    AppConfig.config_save()
