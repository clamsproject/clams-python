import json


class MmifObject(object):
    def __init__(self, mmif_json=None):
        if mmif_json is not None:
            self.deserialize(mmif_json)

    def deserialize(self, mmif):
        raise NotImplementedError()

    def __str__(self):
        return json.dumps(self)

    def pretty(self):
        return json.dumps(self, indent=2)


class Mmif(MmifObject):
    def __init__(self, mmif_json):
        self.context = ''
        self.metadata = {}
        self.input = []
        self.contains = []
        self.views = []
        super().__init__(mmif_json)

    def deserialize(self, mmif):
        in_json = mmif.loads(mmif)

        # TODO (krim @ 10/3/2018): more robust json parsing
        self.context = in_json["context"]
        self.metadata = in_json["metadata"]
        self.input = in_json["input"]
        self.views = in_json["views"]

    def new_view_id(self):
        return 'v_' + str(len(self.views))

    def new_view(self):
        new_view = View(self.new_view_id())
        self.views.append(new_view)
        return new_view


class Annotation(MmifObject):

    def __init__(self, iden, at_type=''):
        # TODO (krim @ 10/4/2018): try deserialize "iden", then if fails defaults to 0s
        self.start = 0
        self.end = 0
        self.feature = {}
        self.iden = iden
        self.attype = at_type

    def deserialize(self, mmif):
        pass


class View(object):

    def __init__(self, iden):
        self.iden = iden
        self.contains = {}
        self.annotations = []

    def new_contain(self, at_type):
        new_contain = Contain(at_type)
        self.contains[at_type] = new_contain
        return new_contain

    def new_annotation(self, aid):
        new_annotation = Annotation(aid)
        self.annotations.append(new_annotation)
        return new_annotation


class Contain(object):

    def __init__(self, at_type):
        self.at_type = at_type
        self.producer = ''
        self.gen_time = None     # datetime.datetime

