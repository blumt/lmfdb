# -*- coding: utf-8 -*-
#*****************************************************************************
#  Copyright (C) 2010 Fredrik Strömberg <fredrik314@gmail.com>,
#  Stephan Ehlen <>
#  Distributed under the terms of the GNU General Public License (GPL)
#
#    This code is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    General Public License for more details.
#
#  The full text of the GPL is available at:
#
#                  http://www.gnu.org/licenses/
#*****************************************************************************
r""" Class for newforms in format which can be presented on the web easily


AUTHORS:

 - Fredrik Stroemberg
 - Stephan Ehlen


NOTE: We are now working completely with the Conrey naming scheme.
 
TODO:
Fix complex characters. I.e. embedddings and galois conjugates in a consistent way.

"""
from flask import url_for
from sage.all import dumps,loads, euler_phi
from lmfdb.modular_forms.elliptic_modular_forms import emf_logger,emf_version
from sage.rings.number_field.number_field_base import NumberField as NumberField_class
from sage.all import copy

from sage.structure.unique_representation import CachedRepresentation
from lmfdb.utils import url_character
from lmfdb.modular_forms.elliptic_modular_forms.backend.web_object import WebObject, WebProperty, WebInt, WebProperties, WebStr, WebNoStoreObject, WebDict, WebFloat

from lmfdb.modular_forms.elliptic_modular_forms.backend import connect_to_modularforms_db,get_files_from_gridfs
try:
    from dirichlet_conrey import *
except:
    emf_logger.critical("Could not import dirichlet_conrey!")

import logging
emf_logger.setLevel(logging.DEBUG)

class WebCharProperty(WebInt):
    def __init__(self, name, modulus=1, default_value=1, **kwargs):        
        self.modulus = modulus        
        if isinstance(default_value, WebChar):
            emf_logger.debug('got WebChar {0}'.format(default_value))
            c = default_value
        else:
            c = WebChar(self.modulus, default_value, update_from_db=True, compute=True)
        super(WebCharProperty, self).__init__(name, default_value = c, **kwargs)

    def to_store(self, c):
        if not isinstance(c, WebChar) \
               and not isinstance(c, DirichletCharacter_conrey):
            return int(c)
        if isinstance(c,WebChar):
            return int(c.number)
        else:
            return int(c.number())

    def from_store(self, n):
        emf_logger.debug('converting {0} from store in WebCharProperty {1}'.format(n, self.name))
        return WebChar(self.modulus, n, compute=True)

    def from_meta(self, n):
        return self.from_store(n)

    def to_meta(self, c):
        return self.to_store(c)
    
class WebChar(WebObject, CachedRepresentation):
    r"""
    Class which should/might be replaced with 
    WebDirichletCharcter once this is ok.
    
    """
    def __init__(self, modulus=1, number=1, update_from_db=True, compute=False):
        self._properties = WebProperties(
            WebInt('conductor'),
            WebInt('modulus', default_value=modulus),
            WebInt('number', default_value=number),
            WebInt('modulus_euler_phi'),
            WebInt('order'),
            WebStr('latex_name', store=True, meta=False),
            WebNoStoreObject('sage_character', DirichletCharacter),
            WebDict('_values_algebraic'),
            WebDict('_values_float'),
            WebDict('_embeddings'),            
            WebFloat('version', default_value=float(emf_version))
            )
        super(WebChar, self).__init__(
            params=['modulus', 'number'],
            dbkey=['modulus', 'number'],
            collection_name='webchar_test',
            update_from_db=update_from_db
            )
        if compute:
            self.compute(save=True)            
        #emf_logger.debug('In WebChar, self.__dict__ = {0}'.format(self.__dict__))
        emf_logger.debug('In WebChar, self.number = {0}'.format(self.number))

    def compute(self, save=True):
        emf_logger.debug('in compute for WebChar number {0} of modulus {1}'.format(self.number, self.modulus))
        c = self.character
        changed = False
        if self.conductor == 0:            
            self.conductor = c.conductor()
            changed = True
        if self.order == 0:
            self.order = c.multiplicative_order()
            changed = True
        if self.latex_name == '':
            self.latex_name = "\chi_{" + str(self.modulus) + "}(" + str(self.number) + ", \cdot)"
            changed = True
        if self._values_algebraic == {} or self._values_float == {}:
            changed = True
            for i in range(self.modulus):
                self.value(i,value_format='float')
                self.value(i,value_format='algebraic')
        if self.modulus_euler_phi == 0:
            changed = True
            self.modulus_euler_phi = euler_phi(self.modulus)
        if changed and save:
            self.save_to_db()
        else:            
            emf_logger.debug('Not saving.')

    def init_dynamic_properties(self):
        if self.number is not None:            
            emf_logger.debug('number: {0}'.format(self.number))
            self.character = DirichletCharacter_conrey(DirichletGroup_conrey(self.modulus),self.number)
            self.sage_character = self.character.sage_character()
            self.name = "Character nr. {0} of modulus {1}".format(self.number,self.modulus)

    def is_trivial(self):
        r"""
        Check if self is trivial.
        """        
        return self.character.is_trivial()

    def embeddings(self):
        r"""
          Returns a dictionary that maps the Conrey numbers
          of the Dirichlet characters in the Galois orbit of ```self```
          to the powers of $\zeta_{\phi(N)}$ so that the corresponding
          embeddings map the labels.

          Let $\zeta_{\phi(N)}$ be the generator of the cyclotomic field
          of $N$-th roots of unity which is the base field
          for the coefficients of a modular form contained in the database.
          Considering the space $S_k(N,\chi)$, where $\chi = \chi_N(m, \cdot)$,
          if embeddings()[m] = n, then $\zeta_{\phi(N)}$ is mapped to
          $\mathrm{exp}(2\pi i n /\phi(N))$.
        """
        return self._embeddings

    def set_embeddings(self, d):
        self._embeddings = d

    def embedding(self):
        r"""
          Let $\zeta_{\phi(N)}$ be the generator of the cyclotomic field
          of $N$-th roots of unity which is the base field
          for the coefficients of a modular form contained in the database.
          If ```self``` is given as $\chi = \chi_N(m, \cdot)$ in the Conrey naming scheme,
          then we have to apply the map
          \[
            \zeta_{\phi(N)} \mapsto \mathrm{exp}(2\pi i n /\phi(N))
          \]
          to the coefficients of normalized newforms in $S_k(N,\chi)$
          as in the database in order to obtain the coefficients corresponding to ```self```
          (that is to elements in $S_k(N,\chi)$).
        """
        return self._embeddings[self.number]
            
    def __repr__(self):
        r"""
        Return the string representation of the character of self.
        """
        return self.name
            
    def value(self, x, value_format='algebraic'):
        r"""
        Return the value of self as an algebraic integer or float.
        """
        x = int(x)
        if value_format =='algebraic':
            if self._values_algebraic is None:
                self._values_algebraic = {}
            y = self._values_algebraic.get(x)
            if y is None:
                y = self._values_algebraic[x]=self.sage_character(x)
            else:
                self._values_algebraic[x]=y
            return self._values_algebraic[x]
        elif value_format=='float':  ## floating point
            if self._values_float is None:
                self._values_float = {}
            y = self._values_float.get(x)
            if y is None:
                y = self._values_float[x]=self.character(x)
            else:
                self._values_float[x]=y
            return self._values_float[x]
        else:
            raise ValueError,"Format {0} is not known!".format(value_format)
        
    def url(self):
        r"""
        Return the url of self.
        """
        if hasattr(self, '_url') and self._url is None:
            self._url = url_character(type='Dirichlet',modulus=self.modulus, number=self.number)
        return self._url
    
   
