#! /usr/bin/env python

# Copyright (c) 2012 Victor Terron. All rights reserved.
# Institute of Astrophysics of Andalusia, IAA-CSIC
#
# This file is part of LEMON.
#
# LEMON is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import calendar
import collections
import lxml.etree
import operator
import os.path
import time

# LEMON modules
import methods
import passband

def validate_dtd(path):
    """ Validate an XML file against a DTD.

    The method validates an Extensible Markup Language (XML) against a Document
    Type Definition (DTD) referenced by the document, raising the appropriate
    exception if an error is encountered, and doing nothing otherwise.

    """

    dtd_parser = lxml.etree.XMLParser(dtd_validation = True)
    lxml.etree.parse(path, dtd_parser)

def setup_header(xml_content, dtd):
    """ Add to an XML file the creation time and the Document Type Definition.

    Receive a string with the contents of an XML file and insert after the
    header (1) a comment with the current time, in UTC, labeled as the creation
    date of the file, and (2) the Document Type Definition (DTD). Because of
    (1), this method is expected to be called right before the XML file is
    written to disk.

    """

    lines = xml_content.split('\n')
    comment = "<!-- File generated by LEMON on %s -->" % methods.utctime()
    lines.insert(1, comment)
    lines = lines[:2] + dtd + lines[2:]
    return '\n'.join(lines)


class XMLOffset(object):
    """ The translation offset between two FITS images.

    This class encapsulates the translation offset between two images, the
    'reference' one and the 'shifted' one, which displacement is given, in
    pixels, in terms of the reference image.

    """

    def __init__(self, reference, shifted, object_, shifted_filter,
                 shifted_date, shifted_fwhm, shifted_airmass,
                 x_offset, y_offset, x_overlap, y_overlap):
        """ Instantiation method for the XMLOffset class.

        reference - the path to the reference, 'unmoved' FITS image.
        shifted - the path to the displaced FITS image.
        object_ - the name of the observed object in the shifted image.
        shifted_filter - the photometric filter of the shifted image,
                         encapsulated as a passband.Passband instance.
        shifted_date - the data of observation of the shifted image, in
                       seconds after the Unix epoch (aka Unix time)
        shifted_fwhm - full width at half maximum of the shifted image
        shifted_airmass - the airmass of the shifted image.
        x_offset - the offset, in pixels, in the x-axis.
        y_offset - the offset, in pixels, in the y-axis.
        x_overlap - the number of stars that overlapped in the x-axis when
                    the offset was calculated and the images were aligned.
        y_overlap - the number of stars that overlapped in the y-axis when
                    the offset was calculated and the images were aligned.

        """

        self.reference = reference
        self.shifted   = shifted
        self.object    = object_
        self.filter    = shifted_filter
        self.date      = shifted_date
        self.fwhm      = shifted_fwhm
        self.airmass   = shifted_airmass
        self.x         = x_offset
        self.y         = y_offset
        self.x_overlap = x_overlap
        self.y_overlap = y_overlap

    def __cmp__(self, other):
        """ Comparison operation, sorts XMLOffset instances by their date """
        return self.date - other.date


class XMLOffsetFile(list):
    """ A collection of XMLOffset instances with the same reference image.

    This class is used as a container of XMLOffset instances that share their
    reference image, whose XML representation can be written to an XML file and
    also read from it. These XML files are self-contained, which means that the
    DTD declaration is at the top of the document, right after the XML
    declaration.

    Note that, although kept in memory in seconds after the Unix epoch, dates
    are written to disk, for user's convenience, as a string of the following
    form: 'Sun Jun 20 23:21:05 1993 UTC' (Coordinated Universal Time).

    """

    STRPTIME_FORMAT = "%a %b %d %H:%M:%S %Y UTC" # default format + 'UTC'

    XML_DTD = [
    "",
    "<!DOCTYPE offsets [",
    "<!ELEMENT offsets (reference, offset+)>",
    "<!ATTLIST offsets size CDATA  #REQUIRED>",
    "",
    "<!ELEMENT reference (image)>",
    "<!ELEMENT offset (image, x_offset, y_offset)>",
    "<!ELEMENT image (path, date, filter, object, fwhm, airmass)>",
    "<!ELEMENT path (#PCDATA)>",
    "<!ELEMENT date (#PCDATA)>",
    "<!ELEMENT filter (#PCDATA)>",
    "<!ELEMENT object (#PCDATA)>",
    "<!ELEMENT fwhm (#PCDATA)>",
    "<!ELEMENT airmass (#PCDATA)>",
    "<!ELEMENT x_offset  (#PCDATA)>",
    "<!ATTLIST x_offset overlap CDATA #REQUIRED>",
    "<!ELEMENT y_offset  (#PCDATA)>",
    "<!ATTLIST y_offset overlap CDATA #REQUIRED>",
    "]>",
    ""]

    def __init__(self, reference_path, date, filter_, object_, fwhm, airmass):
        """ Instantiation method for the XMLOffset class.

        The 'reference_path', 'date', 'filter_', 'object', 'fwhm' and 'airmass'
        arguments are the (1) path, (2) date of observation, (3) photometric
        filter, (4) astronomical target object, (5) full width at half maximum
        and (6) airmass of the reference image, respectively. These values are
        stored in an internal attribute called 'reference', so, for example, in
        order to get the path to the reference image we have to access
        XMLOffset.reference['path'].

        """

        kwargs = {'path' : reference_path, 'date' : date, 'filter' : filter_,
                  'object' : object_, 'fwhm' : fwhm, 'airmass' : airmass}
        self.reference = dict(**kwargs)
        super(XMLOffsetFile, self).__init__()

    def add(self, offset):
        """ Add an XMLOffset to the end of the XML file.

        The method raises ValueError if the reference image of the XMLOffset is
        different that that of the XMLOffsets already in the object. Although
        it is also possible to add an offset using the insert method (as list
        is the parent class), this method should be preferred as it guarantees
        that all the XMLOffsets in the file have the same reference image.

        """

        if offset.reference != self.reference['path']:
            msg = "reference image differs from that of XMLOffsetFile"
            raise ValueError(msg)

        super(XMLOffsetFile, self).append(offset)

    def _toxml(self, encoding = 'utf-8'):
        """ Return the XML representation of the XMLOffsets.

        The method returns a string with the standalone XML representation of
        the XMLOffsets that have been added to the instance, ready to be
        written to disk. Includes the XML header and the DTD declaration.
        """

        root = lxml.etree.Element('offsets')
        root.set('size', str(len(self)))

        def build_image_element(path, date, filter_, object_, fwhm, airmass):
            """ Return the lxml.etree with the 'image' XML node.

            For example, given the parameters './data/ferM_016_obfs.fits',
            1329174680, passband.Passband('Johnson I'), 'ngc2264_1minI', 5.722
            and 1.134, the returned lxml.etree would be the following:

            <image>
              <path>./data/ferM_016_obfs.fits</path>
              <date>Mon Feb 13 23:11:20 2012 UTC</date>
              <filter>Johnson I</filter>
              <object>ngc2264_1minI</object>
              <fwhm>5.722</fwhm>
              <airmass>1.134</airmass>
            </image>

            """

            image = lxml.etree.Element('image')
            path_element = lxml.etree.Element('path')
            path_element.text = path
            image.append(path_element)

            date_element = lxml.etree.Element('date')
            date_element.text = methods.utctime(date)
            image.append(date_element)

            filter_element = lxml.etree.Element('filter')
            filter_element.text = str(filter_)
            image.append(filter_element)

            object_element = lxml.etree.Element('object')
            object_element.text = str(object_)
            image.append(object_element)

            fwhm_element = lxml.etree.Element('fwhm')
            fwhm_element.text = str(fwhm)
            image.append(fwhm_element)

            airmass_element = lxml.etree.Element('airmass')
            airmass_element.text = str(airmass)
            image.append(airmass_element)
            return image

        reference_element = lxml.etree.Element('reference')
        keys = ('path', 'date', 'filter', 'object', 'fwhm', 'airmass')
        args = [self.reference[k] for k in keys]
        image = build_image_element(*args)
        reference_element.append(image)
        root.append(reference_element)

        for offset in self:

            element = lxml.etree.Element('offset')
            attrs = ['shifted', 'date', 'filter', 'object', 'fwhm', 'airmass']
            args = [getattr(offset, a) for a in attrs]
            image = build_image_element(*args)
            element.append(image)

            x = lxml.etree.Element('x_offset', overlap = str(offset.x_overlap))
            x.text = str(offset.x)
            element.append(x)

            y = lxml.etree.Element('y_offset', overlap = str(offset.y_overlap))
            y.text = str(offset.y)
            element.append(y)

            root.append(element)

        kwargs = {'encoding' : encoding, 'xml_declaration': True,
                  'pretty_print' : True, 'standalone' : True}
        xml_content = lxml.etree.tostring(root, **kwargs)
        return setup_header(xml_content, self.XML_DTD)

    def dump(self, path, encoding = 'utf-8'):
        """ Write the XMLOffsets to an XML file.

        The method saves the XMLOffsets to a standalone XML file, silently
        overwriting it if it already exists. The output document includes
        the XML header and the DTD declaration.

        """

        with open(path, 'wt') as fd:
            fd.write(self._toxml(encoding = encoding))
        validate_dtd(path)

    @classmethod
    def load(cls, xml_path):
        """ Load an XMLOffsetFile object from an XML file.

        The opposite of dump, this class method parses 'xml_path', reading the
        XMLOffsetFile object and returning it. The XML files generated by LEMON
        are always standalone documents, meaning that the (DTD) Document Type
        Definition is also included. If the XML file cannot be validated, the
        appropriate exception will be raised.

        """

        # There is no need to open the file to parse it with lxml, but we do it
        # here to check that it exists and is readable by the user. This gives
        # us a clearer error message than what lxml would raise if it failed
        # because the file did not exist (it would be something like "Error
        # reading file: failed to load external entity)
        with open(xml_path, 'r') as _: pass
        root = lxml.etree.parse(xml_path).getroot()

        def get_child(element, tag):
            """ Return the first child of 'element' with tag 'tag' """
            return element.getiterator(tag = tag).next()

        def parse_image_element(element):
            """ Extractt eh values from a lxml.etree with the 'image' XML node.

            For example, given the following lxml.etree...

            <image>
              <path>./data/ferM_016_obfs.fits</path>
              <date>Mon Feb 13 23:11:20 2012 UTC</date>
              <filter>Johnson I</filter>
              <object>ngc2264_1minI</object>
              <fwhm>5.722</fwhm>
              <airmass>1.134</airmass>
            </image>

            ... the six-element tuple ('./data/ferM_016_obfs.fits', 1329174680,
            passband.Passband('Johnson I'), 'ngc2264_1minI', 5.722, 1.134)
            would be returned.

            """

            path = get_child(element, 'path').text

            # From string to struct_time in UTC to Unix seconds
            date_str = get_child(element, 'date').text
            args = date_str, cls.STRPTIME_FORMAT
            date = calendar.timegm(time.strptime(*args))

            filter_str = get_child(element, 'filter').text
            filter_ = passband.Passband(filter_str)
            object_ = get_child(element, 'object').text
            fwhm = float(get_child(element, 'fwhm').text)
            airmass = float(get_child(element, 'airmass').text)

            return path, date, filter_, object_, fwhm, airmass

        reference = get_child(root, 'reference')
        args = parse_image_element(get_child(reference, 'image'))
        offset_file = cls(*args)

        for offset in root.getiterator(tag = 'offset'):

            args = [offset_file.reference['path']]

            image = get_child(offset, 'image')
            path, date, filter_, object_, fwhm, airmass = \
              parse_image_element(image)
            args += [path, object_, filter_, date, fwhm, airmass]

            element = get_child(offset, 'x_offset')
            x_offset = float(element.text)
            x_overlap = int(element.get('overlap'))

            element = get_child(offset, 'y_offset')
            y_offset = float(element.text)
            y_overlap = int(element.get('overlap'))
            args += [x_offset, y_offset, x_overlap, y_overlap]

            offset_file.append(XMLOffset(*args))

        return offset_file


class CandidateAnnuli(object):
    """ Encapsulates the quality of a set of photometric parameters.

    How do we determine how 'good' a set of aperture, annulus and dannulus
    values are for photometry? What we do is to look at the median (or even the
    arithmetic mean, for this matter both approaches are statistically sound)
    standard deviation of the light curves of the most constant stars. It
    follows that the better (i.e., most appropiate for the images being
    reduced) the parameters, the lower this standard deviation will be.

    This class simply encapsulates these four values. You may think of it as a
    surjective function (as two different sets of parameters may result in the
    same values) which links a three-element tuple with the parameters used for
    photometry (aperture, annulus, dannulus) to the standard deviation of the
    light curves of the most constant stars.

    """

    XML_DTD = [
    "",
    "<!DOCTYPE annuli [",
    "<!ELEMENT annuli (band*)>",
    "",
    "<!ELEMENT band (candidate*)>",
    "<!ATTLIST band name     CDATA #REQUIRED>",
    "<!ATTLIST band aperture CDATA #REQUIRED>",
    "<!ATTLIST band annulus  CDATA #REQUIRED>",
    "<!ATTLIST band dannulus CDATA #REQUIRED>",
    "<!ATTLIST band stdev    CDATA #REQUIRED>",
    "",
    "<!ELEMENT candidate EMPTY>",
    "<!ATTLIST candidate aperture CDATA #REQUIRED>",
    "<!ATTLIST candidate annulus  CDATA #REQUIRED>",
    "<!ATTLIST candidate dannulus CDATA #REQUIRED>",
    "<!ATTLIST candidate stdev    CDATA #REQUIRED>",
    "]>",
    ""]


    def __init__(self, aperture, annulus, dannulus, stdev):
        """ Instantiation method.

        aperture - the aperture radius, in pixels.
        annulus - the inner radius of the sky annulus, in pixels.
        dannulus - the width of the sky annulus, in pixels.
        stdev - the median, arithmetic mean or a similar statistical measure
                of the standard deviation of the light curves of the evaluated
                stars when photometry is done using these aperture, annulus
                and dannulus values.

        """

        self.aperture = aperture
        self.annulus  = annulus
        self.dannulus = dannulus
        self.stdev    = stdev

    def __eq__(self, other):
        return self.aperture == other.aperture and \
               self.annulus == other.annulus and \
               self.dannulus == other.dannulus and \
               self.stdev == other.stdev

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "%s(%f, %f, %f, %f)" % (self.__class__.__name__, self.aperture,
                                       self.annulus, self.dannulus, self.stdev)

    @classmethod
    def xml_dump(cls, xml_path, annuli, encoding = 'utf-8'):
        """ Save multiple CadidateAnnuli instances to an XML file.

        This method dumps to a file the XML representation of a dictionary
        which maps each photometric filter to a list of the CandidateInstances
        that for it were evaluated. This offers a functionality similar to that
        of the pickle module, with the additional advantages of being
        human-readable, easily understood and parseable virtually everywhere.

        The generated XML file is a standalone document, which means that the
        Document Type Definitions (DTD), defining the document structure with a
        list of legal elements, is also included. This information is used by
        the XML processor in order to validate the code.

        xml_path - the path to which to save the XML file. Any existing file
                   will be mercilessly overwritten without warning.
        annuli - a dictionary mapping each photometric filter to a list of
                 CandidateInstances, encapsulating the quality of a set of
                 photometric parameters.
        encoding - the character encoding system to use.

        """

        root = lxml.etree.Element('annuli')

        for pfilter in sorted(annuli.iterkeys()):

            # Identify the candidate parameters for which the standard
            # deviation of the curves of the most constant stars is minimal.
            best = min(annuli[pfilter], key = operator.attrgetter('stdev'))

            # Three attributes (i.e., values within the start-tag) identify the
            # optimal photometric parameters for this photometric filters. In
            # this manner, the aperture and sky annuli that have to be used for
            # this photometric filter can be directly and easily extracted from
            # the XML tree. The median or arithmetic mean of the standard
            # deviation of the light curves of the constant stars when
            # photometry was done in order to evaluate these parameters
            # is also stored for debugging purposes.

            kwargs = {'name' : pfilter.name,
                      'aperture' : '%.5f' % best.aperture,
                      'annulus' : '%.5f' % best.annulus,
                      'dannulus' : '%.5f' % best.dannulus,
                      'stdev' : '%.8f' % best.stdev}
            band_element = lxml.etree.Element('band', **kwargs)

            # Although most of the time only the optimal photometric parameters
            # will be of interest, it is also worth saving all the aperture and
            # sky annuli that were evaluated and the median or mean stardard
            # deviation that resulted from using them. Note that the optimal
            # parameters are included here again, as the purpose of this
            # listing is to provide a compendium of all the photometric
            # parameters that were taken into consideration. The photometric
            # parameters will be listed sorted on two keys: the aperture
            # annulus itself (primary) and the sky annulus (secondary).

            annuli[pfilter].sort(key = operator.attrgetter('annulus', 'aperture'))
            for candidate in annuli[pfilter]:
                kwargs = {'aperture' : '%.5f' % candidate.aperture,
                          'annulus' : '%.5f' % candidate.annulus,
                          'dannulus' : '%.5f' % candidate.dannulus,
                          'stdev' : '%.8f' % candidate.stdev}
                cand_element = lxml.etree.Element('candidate', **kwargs)
                band_element.append(cand_element)

            root.append(band_element)

        kwargs = {'encoding' : encoding, 'xml_declaration': True,
                  'pretty_print' : True, 'standalone' : True}
        xml_content = lxml.etree.tostring(root, **kwargs)
        xml_content = setup_header(xml_content, cls.XML_DTD)

        with open(xml_path, 'wt') as fd:
            fd.write(xml_content)
        validate_dtd(xml_path)


    @staticmethod
    def xml_load(xml_path, best_only = False):
        """ Load a series of CandidateAnnuli instances from an XML file.

        This method reverses the functionality of xml_dump(), reading an XML
        file and returning a dictionary which maps each photometric filter to
        a list of the CandidateAnnuli instances that were saved to it.

        By default, all the photometric parameters (encapsulated as
        CandidateAnnuli) that were evaluated for each passband are returned. In
        case only the best (and thus the ones that in theory should be used for
        photometry) are of interest, 'best_only' should be set to True so that
        only the optimal CandidateAnnuli for each passband is parsed.

        The XML files generated by LEMON are always standalone documents,
        meaning that the Document Type Definitions (DTD), defining the document
        structure with a list of legal elements, are also included. If the XML
        file cannot be validated, the appropiate exception will be raised.

        xml_path - the path to the XML file to which the CandidateAnnuli
                   instances were saved and from which they will be now loaded.

        Keyword arguments:
        best_only - if True, only the optimal CandidateAnnuli for for each
                    photometric filter is parsed. Otherwise the entire XML
                    file (and thus all the Cxinstances) are loaded.

        """

        with open(xml_path, 'r') as _: pass
        root = lxml.etree.parse(xml_path).getroot()

        # For each passband, the optimal aperture and sky annuli are stored
        # as attributes of the <band> entity, so that they can be directly
        # extracted in case we are only interested in the optimal paramaters
        # for photometry. Note that, when all the candidate annuli are to be
        # extracted, these attributes can be safely ignored, as the best
        # parameters are also listed as <candidate> entities for each
        # photometric passband.

        annuli = collections.defaultdict(list)
        for band in root:
            pfilter = passband.Passband(band.get('name'))
            attrs = 'aperture', 'annulus', 'dannulus', 'stdev'
            if best_only:
                best = CandidateAnnuli(*[float(band.get(x)) for x in attrs])
                annuli[pfilter].append(best)

            else:
                for candidate in band:
                    cand = CandidateAnnuli(*[float(candidate.get(x)) for x in attrs])
                    annuli[pfilter].append(cand)

        return annuli
