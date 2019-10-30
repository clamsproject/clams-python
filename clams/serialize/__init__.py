import datetime
import json


class MmifObject(object):
    def __init__(self, mmif_json=None):
        if mmif_json is not None:
            self.deserialize(mmif_json)

    def serialize(self):
        return self.__dict__

    def deserialize(self, mmif):
        raise NotImplementedError()

    def __str__(self):
        return json.dumps(self.serialize(), cls=MmifObjectEncoder)

    def pretty(self):
        return json.dumps(self, indent=2, cls=MmifObjectEncoder)


class MmifObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'serialize'):
            return obj.serialize()
        elif hasattr(obj, '__str__'):
            return str(obj)
        else:
            return json.JSONEncoder.default(self, obj)


class Mmif(MmifObject):
    context: str
    metadata: dict
    media: list
    contains: dict
    views: list

    def __init__(self, mmif_json=None):
        self.context = ''
        self.metadata = {}
        self.media = []
        self.contains = {}
        self.views = []
        super().__init__(mmif_json)

    def serialize(self):
        d = self.__dict__.copy()
        d['@context'] = d.pop('context')
        return d

    def deserialize(self, mmif):
        in_json = json.loads(mmif)

        self.context = in_json["@context"]
        self.contains = in_json["contains"]
        self.metadata = in_json["metadata"]
        self.media = in_json["media"]
        self.views = [View(view_str) for view_str in in_json["views"]]

    def new_view_id(self):
        return 'v_' + str(len(self.views))

    def new_view(self):
        new_view = View(self.new_view_id())
        self.views.append(new_view)
        return new_view

    # TODO (krim @ 9/29/19): any tool that calls this needs to be updated
    def add_media(self, medium):
        if not self.get_medium_location(medium):
            self.media.append(medium)
        else:
            raise Exception(f"'{medium.type}' type media is already specified.")

    def get_medium_location(self, md_type):
        for medium in self.media:
            if medium["type"] == md_type:
                return medium["location"]
        raise Exception(f"'{md_type}' type media not found.")

    def get_view_by_id(self, id):
        for view in self.views:
            if view.id == id:
                return view
        raise Exception("{} view not found".format(id))

    def get_view_contains(self, attype):
        return self.get_view_by_id(self.contains[attype])


class Medium(MmifObject):
    id: str
    type: str
    location: str
    metadata: dict

    def __init__(self, medium_str=None):
        self.id = None
        self.type = None
        self.location = None
        self.metadata = {}
        super().__init__(medium_str)

    def deserialize(self, medium_str):
        self.id = medium_str['id']
        self.type = medium_str['type']
        self.location = medium_str['location']
        self.metadata = medium_str['metadata']
        pass

    def add_metadata(self, name, value):
        self.metadata[name] = value


class Annotation(MmifObject):
    start: int
    end: int
    feature: dict
    id: str
    attype: str

    def __init__(self, ann_str=None):
        self.id = None
        self.start = 0
        self.end = 0
        self.attype = None
        self.feature = None
        super().__init__(ann_str)

    def deserialize(self, ann_str):
        self.id = ann_str["id"]
        self.start = ann_str["start"]
        self.end = ann_str["end"]
        self.attype = ann_str["attype"]
        self.feature = ann_str["feature"]

    def add_feature(self, name, value):
        self.feature[name] = value


class View(MmifObject):
    id: str
    contains: dict
    annotations: list

    def __init__(self, view_str=None):
        self.id = None
        self.contains = {}
        self.annotations = []
        super().__init__(view_str)

    def deserialize(self, view):
        self.id = view["id"]
        self.contains.update({k: Contain(v) for k, v in view["contains"].items()})
        self.annotations = [Annotation(ann) for ann in view["annotations"]]

    def new_contain(self, at_type, producer=""):
        new_contain = Contain()
        new_contain.gen_time = datetime.datetime.utcnow().isoformat()
        self.contains[at_type] = new_contain
        return new_contain

    def new_annotation(self, aid, attype):
        new_annotation = Annotation()
        new_annotation.id = aid
        new_annotation.attype = attype
        self.annotations.append(new_annotation)
        return new_annotation


class Contain(MmifObject):
    producer: str
    gen_time: str

    def __init__(self, contain_str=None):
        self.producer = ''
        self.gen_time = None     # datetime.datetime
        super().__init__(contain_str)

    def deserialize(self, contain_str):
        self.producer = contain_str["producer"]
        self.gen_time = contain_str["gen_time"]

