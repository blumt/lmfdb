# See genus2_curves/web_g2c.py
# See templates/space.html for how functions are called

from lmfdb.db_backend import db
from lmfdb.number_fields.number_field import field_pretty
from sage.all import latex, ZZ
from sage.databases.cremona import cremona_letter_code, class_to_int
from lmfdb.characters.utils import url_character
from flask import url_for
import re
from collections import defaultdict
NEWLABEL_RE = re.compile(r"^([0-9]+)\.([0-9]+)\.([a-z]+)$")
OLDLABEL_RE = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")
GAMMA1_RE = re.compile(r"^([0-9]+)\.([0-9]+)$")
def valid_label(label):
    return NEWLABEL_RE.match(label) or OLDLABEL_RE.match(label)
def valid_gamma1(label):
    return GAMMA1_RE.match(label)

def common_latex(level, weight, conrey=None, S="S", t=0, typ="", symbolic_chi=False):
    if conrey is None:
        char = ""
    elif symbolic_chi is True:
        char = r", \chi"
    elif symbolic_chi:
        char = ", " + symbolic_chi
    elif conrey == 1:
        char = ""
    else:
        char = r", [\chi_{{{level}}}({conrey}, \cdot)]".format(level=level, conrey=conrey)
    if typ:
        typ = "^{{{typ}}}".format(typ=typ)
    ans = r"{S}_{{{k}}}{typ}(\Gamma_{t}({N}){char})"
    return ans.format(S=S, k=weight, typ=typ, t=t, N=level, char=char)

def character_orbit_label(level, weight, conrey_label):
    """
    Returns the character orbit label for the character given by conrey label and at the given weight
    """
    return db.mf_newspaces.lucky({'char_labels': {'$contains': conrey_label}, 'level': level, 'weight': weight}, projection='char_orbit_label')

def minimal_conrey_in_character_orbit(level, weight, char_orbit):
    if isinstance(char_orbit, basestring):
        char_orbit = class_to_int(char_orbit) + 1
    res = db.mf_newspaces.lucky({'level': level, 'weight': weight, 'char_orbit_index':char_orbit}, projection='char_labels')
    return None if res is None else res[0]

def convert_spacelabel_from_conrey(spacelabel_conrey):
    """
    Returns the label for the space using the orbit index
    eg:
        N.k.c --> N.k.i
    """
    N, k, chi = map(int, spacelabel_conrey.split('.'))
    return db.mf_newspaces.lucky({'char_labels': {'$contains': chi}, 'level': N, 'weight': k}, projection='label')

def spacelabel_conrey_exists(spacelabel_conrey):
    return convert_spacelabel_from_conrey(spacelabel_conrey) is not None

class DimGrid(object):
    def __init__(self, grid=None):
        if grid is None:
            self._grid = {'M':{'all':0,'new':0,'old':0},
                          'S':{'all':0,'new':0,'old':0},
                          'E':{'all':0,'new':0,'old':0}}
        else:
            self._grid = grid

    def __getitem__(self, X):
        return self._grid[X]

    def __add__(self, other):
        if isinstance(other,int) and other == 0: # So that we can do sum(grids)
            return self
        elif isinstance(other,DimGrid):
            grid = {}
            for X in ['M','S','E']:
                grid[X] = {}
                for typ in ['all','new','old']:
                    grid[X][typ] = self._grid[X][typ] + other._grid[X][typ]
            return DimGrid(grid)
        else:
            raise TypeError

    def __mul__(self, other):
        if isinstance(other, int):
            grid = {}
            for X in ['M','S','E']:
                grid[X] = {}
                for typ in ['all','new','old']:
                    grid[X][typ] = other * self._grid[X][typ]
            return DimGrid(grid)
        else:
            raise TypeError

    def __radd__(self, other):
        return self.__add__(other)

    def __rmul__(self, other):
        return self.__mul__(other)

    @staticmethod
    def from_db(data):
        grid = {'M':{'all':data['mf_dim'],
                     'new':data['dim']+data['eis_new_dim'],
                     'old':data['mf_dim']-data['dim']-data['eis_new_dim']},
                'S':{'all':data['cusp_dim'],
                     'new':data['dim'],
                     'old':data['cusp_dim']-data['dim']},
                'E':{'all':data['eis_dim'],
                     'new':data['eis_new_dim'],
                     'old':data['eis_dim']-data['eis_new_dim']}}
        return DimGrid(grid)

class WebNewformSpace(object):
    def __init__(self, data):
        # Need to set mf_dim, eis_dim, cusp_dim, new_dim, old_dim
        self.__dict__.update(data)
        if self.level == 1 or ZZ(self.level).is_prime():
            self.factored_level = ''
        else:
            self.factored_level = ' = ' + ZZ(self.level).factor()._latex_()
        self.char_conrey = self.char_labels[0]
        self.char_conrey_str = '\chi_{%s}(%s,\cdot)' % (self.level, self.char_conrey)
        self.char_conrey_link = url_character(type='Dirichlet', modulus=self.level, number=self.char_conrey)
        self.newforms = db.mf_newforms.search({'space_label':self.label}, projection=2)
        oldspaces = db.mf_subspaces.search({'label':self.label, 'sub_level':{'$ne':self.level}}, ['sub_level', 'sub_char_orbit', 'sub_char_labels', 'sub_mult'])
        self.oldspaces = [(old['sub_level'], old['sub_char_orbit'], old['sub_char_labels'][0], old['sub_mult']) for old in oldspaces]
        self.dim_grid = DimGrid.from_db(data)
        #self.old_dim = self.cusp_dim - self.dim
        #self.eis_old_dim = self.eis_dim - self.eis_new_dim
        self.properties = [
            ('Label',self.label),
            ('Level',str(self.level)),
            ('Weight',str(self.weight)),
            ('Character Orbit',self.char_orbit_label),
            ('Representative Character',r'\(%s\)'%self.char_conrey_str),
            ('Character Field',r'\(\Q%s\)' % ('' if self.char_degree==1 else r'(\zeta_{%s})' % self.char_order)),
            ('Dimension',str(self.dim)),
            ('Sturm Bound',str(self.sturm_bound)),
            ('Trace Bound',self.__dict__.get('trace_bound','?'))
        ]
        self.bread = [
             ('Modular Forms', url_for('mf.modular_form_main_page')),
             ('Classical newforms', url_for(".index")),
             ('Level %s' % self.level, url_for(".by_url_level", level=self.level)),
             ('Weight %s' % self.weight, url_for(".by_url_full_gammma1_space_label", level=self.level, weight=self.weight)),
             ('Character orbit %s' % self.char_orbit_label, url_for(".by_url_space_label", level=self.level, weight=self.weight, char_orbit_label=self.char_orbit_label)),
        ]
        if self.char_labels[0] == 1:
            character_str = "Trivial Character"
        else:
            character_str = r"Character \(\chi_{{{level}}}({conrey}, \cdot)\)".format(level=self.level, conrey=self.char_labels[0])
        self.title = r"Space of Cuspidal Newforms of Weight %s, Level %s and %s"%(self.weight, self.level, character_str)
        self.friends = []

    @staticmethod
    def by_label(label):
        """
        Searches for a specific modular forms space by its label.
        Constructs the WebNewformSpace object if the space is found, raises an error otherwise
        """
        if not valid_label(label):
            raise ValueError("Invalid modular forms space label %s." % label)
        data = db.mf_newspaces.lookup(label)
        if data is None:
            raise ValueError("Space %s not found" % label)
        return WebNewformSpace(data)

    def _vec(self):
        return [self.level, self.weight, self.char_labels[0]]

    def mf_latex(self):
        return common_latex(*(self._vec() + ["M"]))

    def eis_latex(self):
        return common_latex(*(self._vec() + ["E"]))

    def eis_new_latex(self):
        return common_latex(*(self._vec() + ["E",0,"new"]))

    def eis_old_latex(self):
        return common_latex(*(self._vec() + ["E",0,"old"]))

    def cusp_latex(self):
        return common_latex(*(self._vec() + ["S"]))

    def cusp_latex_symbolic(self):
        return common_latex(*(self._vec() + ["S"]), symbolic_chi=True)

    def new_latex(self):
        return common_latex(*(self._vec() + ["S",0,"new"]))

    def old_latex(self):
        return common_latex(*(self._vec() + ["S",0,"old"]))

    def old_latex_symbolic(self):
        return common_latex(*(self._vec() + ["S",0,"old"]), symbolic_chi=True)

    def subspace_latex(self, new=False):
        return common_latex("M", self.weight, self.char_labels[0], "S", 0, "new" if new else "", symbolic_chi=True)

    def oldspace_decomposition(self):
        # Returns a latex string giving the decomposition of the old part.  These come from levels M dividing N, with the conductor of the character dividing M.
        template = r"<a href={url}>\({old}\)</a>\(^{{\oplus {mult}}}\)"
        return r"\(\oplus\)".join(template.format(old=common_latex(N, self.weight, conrey, typ="new"),
                                                  url=url_for(".by_url_space_label",level=N,weight=self.weight,char_orbit_label=cremona_letter_code(i-1)),
                                                  mult=mult)
                                  for N, i, conrey, mult in self.oldspaces)

class WebGamma1Space(object):
    def __init__(self, level, weight):
        self.level = level
        self.weight = weight
        self.odd_weight = bool(self.weight % 2)
        self.label = '%s.%s'%(self.level, self.weight)
        if level == 1 or ZZ(level).is_prime():
            self.factored_level = ''
        else:
            self.factored_level = ' = ' + ZZ(level).factor()._latex_()
        newspaces = list(db.mf_newspaces.search({'level':level, 'weight':weight, 'char_parity':-1 if self.odd_weight else 1}))
        if not newspaces:
            raise ValueError("Space not in database")
        #oldspaces = db.mf_gamma1_subspaces.search({'level':level, 'weight':weight}, ['sub_level','sub_mult'])
        #self.oldspaces = [old['sub_level'],old['sub_mult'] for old in oldspaces]
        self.dim_grid = sum(DimGrid.from_db(space) for space in newspaces)
        self.mf_dim = sum(space['mf_dim'] for space in newspaces)
        self.eis_dim = sum(space['eis_dim'] for space in newspaces)
        self.eis_new_dim = sum(space['eis_new_dim'] for space in newspaces)
        self.eis_old_dim = self.eis_dim - self.eis_new_dim
        self.cusp_dim = sum(space['cusp_dim'] for space in newspaces)
        self.new_dim = sum(space['dim'] for space in newspaces)
        self.old_dim = sum((space['cusp_dim']-space['dim']) for space in newspaces)
        newforms = list(db.mf_newforms.search({'level':level, 'weight':weight}, ['space_label', 'dim', 'level', 'char_orbit_label', 'hecke_orbit']))
        self.decomp = [(space, [form for form in newforms if form['space_label'] == space['label']])
                       for space in newspaces]
        self.properties = [
            ('Label',self.label),
            ('Level',str(self.level)),
            ('Weight',str(self.weight)),
            ('Dimension',str(self.new_dim)),
        ]
        self.bread = [
             ('Modular Forms', url_for('mf.modular_form_main_page')),
             ('Classical newforms', url_for(".index")),
             ('Level %s' % self.level, url_for(".by_url_level", level=self.level)),
             ('Weight %s' % self.weight, url_for(".by_url_full_gammma1_space_label", level=self.level, weight=self.weight)),
        ]
        self.title = r"Space of Cuspidal Newforms of weight %s and level %s"%(self.weight, self.level)
        self.friends = []

    @staticmethod
    def by_label(label):
        match = valid_gamma1(label)
        if not match:
            raise ValueError("Invalid modular forms space label %s." % label)
        level, weight = map(int, match.groups())
        return WebGamma1Space(level, weight)

    def _vec(self):
        return [self.level, self.weight, None]

    def mf_latex(self):
        return common_latex(*(self._vec() + ["M",1]))

    def eis_latex(self):
        return common_latex(*(self._vec() + ["E",1]))

    def eis_new_latex(self):
        return common_latex(*(self._vec() + ["E",1,"new"]))

    def eis_old_latex(self):
        return common_latex(*(self._vec() + ["E",1,"old"]))

    def cusp_latex(self):
        return common_latex(*(self._vec() + ["S",1]))

    def new_latex(self):
        return common_latex(*(self._vec() + ["S",1,"new"]))

    def summand_latex(self,symbolic_chi=True):
        return common_latex(self.level, self.weight, 1, "S", 0, "new", symbolic_chi=symbolic_chi)

    def old_latex(self):
        return common_latex(*(self._vec() + ["S",1,"old"]))

    def header_latex(self):
        return r'\(' + common_latex(*(self._vec() + ["S",0,"new",True])) + '\)'

    def _link(self, N, i=None, form=None, typ="new", label=True):
        if form is not None:
            form = cremona_letter_code(form - 1)
        if label:
            if i is None:
                name = "{N}.{k}".format(N=N, k=self.weight)
            elif form is None:
                name = "{N}.{k}.{i}".format(N=N, k=self.weight, i=i)
            else:
                name = "{N}.{k}.{i}.{f}".format(N=N, k=self.weight, i=i, f=form)
        else:
            t = 1 if i is None else 0
            name = r"\(%s\)" % common_latex(N, self.weight, i, t=t, typ=typ)
        if i is None:
            url = url_for(".by_url_full_gammma1_space_label",
                          level=N, weight=self.weight)
        elif form is None:
            url = url_for(".by_url_space_label",
                          level=N, weight=self.weight, char_orbit_label=i)
        else:
            url = url_for(".by_url_newform_label",
                          level=N, weight=self.weight, char_orbit_label=i, hecke_orbit=form)
        return r"<a href={url}>{name}</a>".format(url=url, name=name)

    def oldspace_decomposition(self):
        template = r"{link}\(^{{\oplus {mult}}}\)"
        return r"\(\oplus\)".join(template.format(link=self._link(N, label=False),
                                                  mult=len(ZZ(self.level//N).divisors()))
                                  for N in ZZ(self.level).divisors() if N != self.level)

    def decomposition(self):
        # returns a list of 6-tuples chi_rep, num_chi, space, firstform, firstdim, forms
        ans = []
        for i, (space, forms) in enumerate(self.decomp):
            rowtype = "oddrow" if i%2 else "evenrow"
            chi_str = r"\chi_{%s}(%s, \cdot)" % (space['level'], space['char_labels'][0])
            chi_rep = '<a href="' + url_for('characters.render_Dirichletwebpage',
                                             modulus=space['level'],
                                             number=space['char_labels'][0])
            chi_rep += '">\({}\)</a>'.format(chi_str)

            num_chi = space['char_degree']
            link = self._link(space['level'], space['char_orbit_label'])
            if not forms:
                ans.append((rowtype, chi_rep, num_chi, link, "No newforms", "", []))
            else:
                dims = [form['dim'] for form in forms]
                forms = [self._link(form['level'], form['char_orbit_label'], form['hecke_orbit']) for form in forms]
                ans.append((rowtype, chi_rep, num_chi, link, forms[0], dims[0], zip(forms[1:], dims[1:])))
        return ans
