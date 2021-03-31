from src.base.actor import configuration
from src.base.log import logger
from src.model.db import connect
from src.model.db.schema import YamlFile


class Test(configuration.Mixin):
    _config = configuration.from_yml('test_config.yml')
    field = _config.field(str)
    dict_one = _config.field(dict)
    dict_two = _config.field(dict)

    def show(self):
        print(self.field)
        print(self.dict_one)
        print(self.dict_two)


if __name__ == '__main__':
    with logger:
        test = Test()
        test.show()
        with connect()() as session:
            YamlFile.update_object(session, test)
        test.show()
