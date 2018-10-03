import json
from abc import ABC, abstractmethod


class ClamApp(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def appmetadata(self):
        raise NotImplementedError()

    @abstractmethod
    def sniff(self, mmif):
        raise NotImplementedError()

    @abstractmethod
    def annotate(self, mmif):
        raise NotImplementedError()


class Mmif(object):
    context = ''
    metadata = {}
    input = []
    contains = []
    views = []

    def __init__(self, json_string):
        self.context = json.loads(json_string)

    def __str__(self):
        json.dumps(self)

    def new_view_id(self):
        return 'v_' + str(len(self.views))

    def new_view(self):
        newview = View(self.new_view_id())
        self.views.append(newview)
        return newview


class Annotation(object):
    iden = ''
    start = 0
    end = 0
    attype = ''
    feature = {}

    def __init__(self, iden, attype=''):
        self.iden = iden
        self.attype = attype


class View(object):
    iden = ''
    contains = {}
    annotations = []

    def __init__(self, iden):
        self.iden = iden

    def new_contain(self, attype):
        newcontain = Contain(attype)
        self.contains[attype] = newcontain
        return newcontain

    def new_annotation(self, aid):
        newannotation = Annotation(aid)
        self.annotations.append(newannotation)
        return newannotation


class Contain(object):
    attype = ''
    producer = ''
    gen_time = None     # datetime.datetime

    def __init__(self, attype):
        self.attype = attype


