import os
import matplotlib as plt
from astropy.table import Table
from astropy.io import fits
from astropy.time import Time
import glob
from wurlitzer import sys_pipes
import pandas as pd
import numpy as np


#TODO: NEED to change the event flagging (filtering on an equality is not sufficient since sometimes you might not care what the value of a flag is)
#A better approach:
#  a) nicerObs should define the information about a NICER observation (path, rmf, arf) - each obs should have its own
# object isinstance
# b) a method should return the events list as a pandas dataframe (with eventflags as a scalar)
# c) we should have a function to filter the events file on event flags - for example filter
# on event type: fast+slow events, fast events, slow events, resests, etc.
# lightcurves and spectra should be defined from the filtered events dataframe



class nicerObs(object):
    """
    Defines a NICER observation Object
    """
    def __init__(self, obsid, rootdir='.', rmffile = '', arffile = ''):
        """
        get the directory structure for a nicer observation as attributes of the class assuming
        the NICER observations are sorted in directories by OBSID and that the
        OBSID directories are subdirectories of a "root" directory

        this assumes that the NICER data are structured as in the archive, i.e.:
        <rootdir>/<obsid>
            auxil   log    xti

        <rootdir>/<obsid>/xti
           event_cl	   event_uf	   hk


        :param obsid: observation id number (str or list)
        :param rootdir: directory location of the OBSIDS
        :param rmffile: name of RMF files (str or list)
        :param arffile: name of ARF files for obsid (str or list)

        """
        rootdir = rootdir.strip()
        if type(obsid) != str:
            obsid = str(int(obsid)).strip()
        else:
            obsid = obsid.strip()
        self.datadir = os.path.join(rootdir, obsid)
        xtidir = os.path.join(self.datadir, 'xti')
        # Check that obsid directory exists
        if not os.path.exists(xtidir):
            print("{xtidir} Not Found; returning".format(xtidir=xtidir))
            return None
        self.xti = xtidir
        self.log = os.path.join(self.datadir, 'log')
        self.aux = os.path.join(self.datadir, 'auxil')
        # TODO: ALLOW LIST OF OBSIDS
        # elif type(obsid)== list:
        #     self.datadir = [os.path.join(rootdir, obs.strip()) for obs in obsid]
        #     self.log = [os.path.join(datadir, 'log') for datadir in self.datadir]
        #     self.aux = [os.path.join(datadir, 'auxil') for datadir in self.datadir]
        #     self.xti = [os.path.join(datadir, 'xti') for datadir in self.datadir]
        if type(rmffile) == str:
            self.rmffile = rmffile
        elif type(rmffile) == list:
            self.rmffile = [r for r in rmffile]
        if type(arffile) == str:
            self.arffile = arffile
        elif type(arffile) == list:
            self.arffile = [a for a in arffile]


    def get_eventfile(self, evttype='cl', mpu=7, evtfile=None):
        """
        return the name of the events file
        :param evttype: "cl" for cleaned events, "ufa" for unfiltered calibrated events, "uf" for unfiltered, uncalibrated events
        :param mpu: mpu should be an integer between 0-6 to specify an individual mpu or 7 for the merged data (default = 7)
        :return: name of the event file
        """
        if not evtfile:
            evttype = evttype.strip()
            if evttype == "cl":
                evdir = os.path.join(self.xti,"event_cl")
                try:
                    evtfile = glob.glob(os.path.join(evdir,"*mpu{0}_cl.evt*".format(mpu)))[-1]
                except:
                    print "Did not find any cleaned event files in {0}".format(evdir)
                    evtfile = ''
                return evtfile
            if evttype == "ufa":
                evdir = os.path.join(self.xti,"event_cl")
                evtfile = glob.glob(os.path.join(evdir,"*mpu{0}_ufa.evt*".format(mpu)))[-1]
                return evtfile
            if evttype == "uf":
                evdir=os.path.join(self.xti,"event_uf")
                evtfile = glob.glob(os.path.join(evdir,"*uf.evt*"))
                # return the unfiltered event file for the specified mpu
                evtfile = [x for x in evtfile if 'mpu{0}'.format(mpu) in x]
                try:
                    evtfile = evtfile[0]
                except:
                    print "Could not find UF events file for mpu {0}".format(mpu)
                    return ''
                return evtfile
            else:
                print "evttype must be either cl, ufa, or uf, not {0}".format(evttype)


    def get_eventsdf(self, evttype='cl', mpu=7, flagtype=None, chanmin=None, chanmax=None,
                     det_id = None):
        """
        returns the events as a pandas dataframe
        :param evttype: type of event file ('cl' = use cleaned events, 'uf' = use uncleaned events,
        'ufa' = use unfiltered, calibrated events)
        :param flagtype: value of event flag for filtering; either 'undershoot', 'overshoot','software', 'fast',
        'slow', 's+f', '1mpu' or None"
        :param mpu: if "uf" or "ufa", mpu should be an integer between 0-6 to specify which mpu is desired (default = 0)
        :param chanmin: minimum pi channel of selected events or None
        :param chanmax: maximum pi channel of selected events or None
        :return:
        """
        efile = self.get_eventfile(mpu=mpu, evttype=evttype)
        try:
            evttab = Table.read(efile,'EVENTS')
        except ValueError:
            # if eventfile name not found
            print("Problem reading {0}; returning".format(efile))
            return -1
        # eflag=self.get_event_flags(evttype=evttype,mpu=mpu)
        # create an events flag column as a string of 1's and 0's
        # kludge using astropy.table since pandas can't handle array columns
        # remove the event flag column from the astropy table then
        # add it back as a string of 1''s and 0's

        # TODO - make flags integers then use bitwise operator & to do the flag comparison
        # see https://www.tutorialspoint.com/python/bitwise_operators_example.htm

        eflags = self.get_event_flags(evttype=evttype, mpu=mpu)

        evttab.remove_column('EVENT_FLAGS')
        evtdf = evttab.to_pandas()
        # Add back in the event flags as a scalar
        evtdf['EVENT_FLAGS'] = eflags
        # if eventflag defined, filter on eventflag

        # TODO: Finish event flagging
        if flagtype != None:
            evtdf = filter_flag(evtdf, flagtype)
        if chanmin:
            # include only events with PI channel greater than chanmin
            evtdf = evtdf[(evtdf.PI >= chanmin)]
        if chanmax:
            # include only events with PI channel greater than chanmin
            evtdf = evtdf[(evtdf.PI <= chanmax)]
        if det_id != None:
            # include only events from the specified detector
            try:
                evtdf = evtdf[(evtdf.DET_ID==det_id)]
            except:
                print "Problem getting Detector ID from events dataframe"
        return evtdf


    def get_prod(self):
        """
        gets the files in the products directory
        """
        prodfiles = glob.glob("{0}/products/*.*".format(self.xti))
        return prodfiles


    def get_hk(self):
        hkfiles = glob.glob("{0}/hk/*.hk".format(self.xti))
        return hkfiles


    def get_gti(self, evttype='cl', mpu=7):
        """
        gets the gti for the cleaned events as a pandas dataframe
        """
        hdu = fits.open(self.get_eventfile(evttype=evttype, mpu=mpu))
        gti = hdu['GTI'].data
        gti = Table(gti)
        gtidf = gti.to_pandas()
        gtidf['Duration'] = gtidf.STOP - gtidf.START
        self.duration = gtidf['STOP'].max() - gtidf['START'].min()
        self.exposure = gtidf.Duration.sum()
        mjdref = Time(hdu['EVENTS'].header['MJDREFI']+ hdu['EVENTS'].header['MJDREFF'],
                      format='mjd')
        startiso = []
        for s in gtidf.START:
            t = mjdref.mjd + s/86400.0
            startiso.append(Time(t, format='mjd').iso)
        gtidf['STARTISO'] = startiso
        stopiso = []
        for s in gtidf.STOP:
            t = mjdref.mjd + s/86400.0
            stopiso.append(Time(t, format='mjd').iso)
        gtidf['STOPISO'] = stopiso
        return gtidf


    def get_event_flags(self, evttype='cl', mpu=7):
        """
        gets the event flag bit values as a numpy array of integers.
        event flag of 24 = 2**3 + 2**4 (a 1 in bit 3 and 4) corresponds to
        events detected by both the fast and slow chains (i.e. the "best" events)

        Valid X-ray events are those detected in the slow chain (i.e. a bit flag of xxx1x000)

        Notes
        1) NICER currently uses 6-bit event flags; the event file however
        has the bit array = 8 bits, since FITS requires a bit array to have an integer number of bytes
        This means that the two highest order (two leftmost) bits are unused

        2) the meaning of the bit flags:
            bit 0 (xxxxxxx1 ==  1): "undershoot" reset
            bit 1 (xxxxxx1x ==  2): "overshoot" reset
            bit 2 (xxxxx1xx ==  4): software sample
            bit 3 (xxxx1xxx ==  8): fast signal chain triggered
            bit 4 (xxx1xxxx == 16): slow signal chain triggered
            bit 5 (xx1xxxxx == 32): first event in MPU packet
            bit 6 (x1xxxxxx): unused
            bit 7 (1xxxxxxx): unused

        :param evttype: type of event (by default use cleaned events)
        :param mpu: Number of  MPU (default is to use the merged data, mpu=7)
        :return:
        """
        efile = self.get_eventfile(evttype, mpu=mpu)
        events=fits.open(efile)[1].data
        event_flags = [x[0] for x in events.EVENT_FLAGS]
        return np.asarray(event_flags)


    def get_event_times(self, evttype="cl", flagtype="slow", mpu=7):
        """
        get the event times from the specified event file
        :return:
        """
        hdu = fits.open(self.get_eventfile(evttype=evttype, mpu=mpu))
        times = hdu[1].data['TIME']
        event_flags = self.get_event_flags(evttype=evttype, mpu=mpu)
        ind = np.where(event_flags == eventflag)[0]
        try:
            times = times[ind]
        except Exception, errmsg:
            print "Problem in event flag filtering for event flag = {0}({1})".format(eventflag, errmsg)
            return
        return times


    def get_lc(self, binwidth, evttype='cl', flagtype="slow", mpu=7, det_id = None,
               chanmin = None, chanmax=None, verbose=False, gtinum=None, evtdf = None):
        """
        return the binned lightcurve (bincounts, bincenters and binwidths)
        for all gtis (or, optionally, selected gtis) in the events file.

        :param binwidth: with of time bin in same unit as tstart and tstop
        :param evttype: type of event file ("cl", "ufa" or "uf")
        :param eventflag: flag for event; default = 2**3 + 2**4 = 24 for fast+slow events
        :param mpu: if evttype = uf, specify which mpu (from 0 to 6) to use; ignored otherwise
        :param chanmin: minimum PI channel to be used in the lightcurve binning (optional)
        :param chanmax: maximum PI channel to be used in the lightcurve binning (optional)
        :param gtinum: specify which gti of which you want to get the lightcurve (None means use all gtis)
        :param evtdf: event file dataframe; if not specified will be read from the event file
        :return: triplet of the binned_counts, bin_centers, and bin_widths

        Usage: (to bin a ligthcurve between 0.0<time<40.0 in widths of 10 seconds
        bincnts, bincen, binwidths  = nobs.get_lc(0.0, 40.0, 10)
        """
        evttype = evttype.strip()
        if evtdf is None:
            evtdf = self.get_eventsdf(evttype=evttype, mpu=mpu, flagtype=flagtype, det_id=det_id)
        gti = self.get_gti()
        if chanmin:
            # include only events with PI channel greater than chanmin
            evtdf = evtdf[(evtdf.PI >= chanmin)]
        if chanmax:
            # include only events with PI channel greater than chanmin
            evtdf = evtdf[(evtdf.PI <= chanmax)]
        #
        # get rate for each gti
        #
        bincnts = []
        bincen = []
        binwidths = []
        tsta = gti.START
        tsto = gti.STOP
        if gtinum != None:
            try:
                tsta = [tsta[gtinum]]
            except:
                print "Can't retrieve start for GTI = {0}; returning".format(gtinum)
                status = -1
                return status
            tsto = [tsto[gtinum]]
        for tstart, tstop in zip(tsta, tsto):
            nbins = int((tstop - tstart)/ binwidth)
            time = np.asarray(evtdf.TIME[(evtdf.TIME >= tstart) & (evtdf.TIME <= tstop)])
            if len(time) > 0:
                if nbins <= 0:
                    if verbose:
                        print "Specified bin width {0} is greater than or equal to total duration of {1}; setting number of bins to 1".format(binwidth, tstop-tstart)
                    nbins = 1
                try:
                    bcnts, bbins = np.histogram(time, nbins)
                except ValueError, errmsg:
                    print "get_lc: ERROR in creating histogram ({0}); nbins = {1} {2} {3}".format(errmsg, nbins, tstop-tstart, binwidth )
                    return [-1,-1]
                if nbins > 1:
                    bwidths =  bbins[1:] - bbins[:-1]
                    bhalfwidth = 0.5 * bwidths
                    bcen = bbins[:-1] + bhalfwidth
                if nbins == 1:
                    bwidths = [tstop - tstart]
                    tdur = tstop - tstart
                    bcen = [tstart + tdur/2.0]
                bincnts.extend(bcnts)
                bincen.extend(bcen)
                binwidths.extend(bwidths)
        return np.asarray(bincnts), np.asarray(bincen), np.asarray(binwidths)

    def fold(self,evttype, period, tstart=0.0, tstop=0.0, epoch=0.0, nbins=100, flagtype="slow", mpu=7):
        """
        return a phase-folded lightcurve
        :param period: period on which to fold
        :param epoch: zero-point of the calculated phase
        :return: lc, phase where 0<phase<1 is the fraction of the period relative to epoch
        """
        time = self.get_event_times(evttype=evttype,flagtype=flagtype,mpu=mpu)
        if tstop > tstart:
            ind = np.where((time >= tstart) & (time <= tstop))
            time = time[ind[0]]
        phase=(time - epoch)/period
        phase = [x-int(x) for x in phase]
        bincnts, binphi = np.histogram(phase, nbins)
        binhalfwidth = 0.5 * (binphi[1:] - binphi[:-1])
        phicen = binphi[:-1] + binhalfwidth
        return bincnts,phicen

    def get_spectrum(self, evttype='cl', mpu=7, binning=1,
                     tstart=None,
                     tstop=None,
                     chantype="PI",
                     flagtype="slow"):
        """
        calculate the binned spectrum optionally between tstart and tstart
        :param evttype:
        :param mpu:
        :param binning: number of channels to bin for output spectrum
        :param tstart: start time in MET
        :param tstart: stop time in MET
        :return: returns a dictionary of the spectrum
        """

        # TODO: using a sample NICER spectrum from XSELECT as a template, write out spectrum as an xspec-formatted PHA file

        # TODO header cards in extension 1 to be changed
        # DATE    = date of file creation (Time.now().fits)
        # EXPOSURE= Exposure time (sum of the gtis)
        # ONTIME  = same as exposure time
        # TARG_ID = NICER target catalog ID number (if known)
        # OBSERVER= Observer or Principal Investigator
        # TITLE   = Science program title
        # OBS_ID  = Observation ID
        # CREATOR = get_spectrum()
        # OBJECT  = 'WR_140  '           / Name of observed object
        # EQUINOX =  Equinox of celestial coord system (2000.0 generally)
        # RADECSYS= 'FK5     '           / celestial coord system
        # RA_NOM  =  R.A. of nominal aspect point [J2000] in deg
        # DEC_NOM =  Dec. of nominal aspect point [J2000] in deg
        # RA_OBJ  = R.A. of target [J2000] in deg
        # DEC_OBJ = Dec. of target [J2000] in deg
        # TSTART  = start of first gti in SC clock units
        # TSTOP   = end of last gti in SC clock units
        # DATE-OBS= ISOT time corresponding to TSTART
        # DATE-END= ISOT time corresponding to TSTOP
        # LIVETIME= On-source time
        # MJD-OBS = MJD corresponding to DATE-OBS
        # USER    = User name of creator
        # LEAP_INIT= should be set = 2 (erroneously set to 0 by pipeline)
        #
        # TODO: header cards to be deleted:
        #
        # FILIN00n (delete)
        # HISTORY (the cards in the template; new history cards should be added)
        # SEQPNUM =                    1 / Number of times the dataset processed
        #
        #
        # TODO: add good time intervals as Extension 2
        rmffile = self.rmffile
        if not os.path.isfile(rmffile):
            print "nicerObs RMF file {0} should exist but doesn't; returning".format(rmffile)
            return
        arffile = self.arffile
        if not os.path.isfile(rmffile):
            print "nicerObs ARF file {0} should exist but doesn't; returning".format(arffile)
            return
        evtdf = self.get_eventsdf(evttype=evttype, mpu=mpu, flagtype=flagtype)
        if not tstart:
            tstart = min(evtdf.TIME)
        if not tstop:
            tstop = max(evtdf.TIME)
        evtDF = evtdf[(evtdf.TIME >= tstart) & ((evtdf.TIME <= tstop))]
        #
        # get gain from RMF file
        #
        # get channels and energy boundaries from the rmf file
        rmf = fits.open(rmffile)
        ebounds = rmf['EBOUNDS'].data
        DE = ebounds.E_MAX - ebounds.E_MIN
        # chan_nrg is the energy of the center of the bin
        chan_nrg = ebounds.E_MIN + DE
        arf = fits.open(arffile)
        effarea = arf['SPECRESP'].data
        # interpolate the effective area to chan_nrg scale
        effarea_interp = np.interp(chan_nrg, effarea.ENERG_LO, effarea.SPECRESP)
        # chanbins are the edges of the channel bins starting at 1
        chanbins = np.arange(1, 1500, binning)
        specpi, chans = np.histogram(evtDF[chantype], bins=chanbins)
        # get the edges of the energy bins corresponding to chanbins
        nrgbins = np.interp(chanbins, ebounds.CHANNEL, chan_nrg)
        specdict = {'Counts':specpi, 'Energy':nrgbins[:-1], 'Channels':chanbins[:-1],
                    'Binning':binning, 'TSTART':tstart, 'TSTOP':tstop}
        return specdict


    def get_detector_rates(self, evttype='cl',mpu=7, chanmin=30, chanmax=12000, flagtype='slow'):
        """
        returns a dataframe of the counts, poissonian errors of the counts, and rates, per detector
        :param evttype: Type of event (cleaned, uf, ufa; cleaned by default)
        :param mpu: number of mpu if uf or ufa chosen
        :param chanmin: minimum pi channel of selected events
        :param chanmax: maximum pi channel of selected events
        :return: detector data frame with detector id as the index, along with counts and rates
        """
        evtdf = self.get_eventsdf(evttype='cl', flagtype=flagtype, mpu=mpu, chanmin=chanmin, chanmax=chanmax,
                     det_id=None)

        if type(evtdf) != int:
            counts_by_detector = pd.DataFrame(evtdf['DET_ID'].groupby(evtdf['DET_ID']).describe()['count'])
            counts_by_detector['sigma'] = np.sqrt(counts_by_detector['count'])
            gtidf = self.get_gti(evttype=evttype, mpu=mpu)
            expo = gtidf['Duration'].sum()
            counts_by_detector['rate'] = counts_by_detector['count']/ expo
            counts_by_detector['rate_err'] = counts_by_detector['sigma'] / expo
            counts_by_detector['Exposure'] = expo
            return counts_by_detector
        else:
            print "Could not find event file for {0}".format(self.obsid)
            return -1


    def append_obs(self, nicerObs):
        """
        append a nicer obs to a nicer obs, and return the combined event list and gtis
        :param nicerObs: nicer observation to append
        :return: combined event
        """
        pass


def filter_flag(eventDF, flagtype='slow'):
    """
    Filter an NICER event dataframe based on the EVENT_FLAGS

    :param eventDF: NICER events dataframe
    :param flagtype: type of flagging to be done.  Valid values are:
            'undershoot': (xxxxxxx1 ==  1) undershoot reset
            'overshoot':  (xxxxxx1x ==  2) overshoot reset
            'software':   (xxxxx1xx ==  4) software sample
            'fast':       (xxxx1000 ==  8) Valid fast trigger
            'slow':       (xxx1x000 == 16) Valid slow trigger
            's+f':        (xxx1x000 == 24) valid fast+slow trigger event
            '1mpu':       (xx1xxxxx == 32) first event in MPU packet

    :return: returns the event dataframe including only the types of events specified
    """
    f = flagtype.strip().lower()
    if flagtype != None:
        if f == 'undershoot':
            # this flags any event with bit 0 set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 1) == 1]
        elif f == 'overshoot':
            # this flags any event with bit 1 set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 2) == 2]
        elif f == 'software':
            # this flags any event with bit 2 set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 4) == 4]
        elif f == 'fast':
            # this flags any event with bit 3 set and bit 0, 1, 2 not set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 8) == 8]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 1) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 2) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 4) == 0]
        elif f == 'slow':
            # this flags any event with bit 4 set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 16) == 16]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 1) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 2) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 4) == 0]
        elif f == '1mpu':
            # this flags any event with bit 5 set
            evtDFfilt = eventDF[(eventDF.EVENT_FLAGS & 32) == 32]
        elif f == 's+f':
            # this flags fast+slow triggers
            evtDFfilt = eventDF[eventDF.EVENT_FLAGS == 24]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 1) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 2) == 0]
            evtDFfilt = evtDFfilt[(evtDFfilt.EVENT_FLAGS & 4) == 0]
        else:
            print("flagtype must be either 'undershoot', 'overshoot','software', 'fast', 'slow', 's+f', or '1mpu'")
            return
        return evtDFfilt
    else:
        return eventDF


def parse_nicer_flag(filter_flag):
    """
    translates a NICER bit event flag & prints result
    :param filter_flag: specified nicer filter flag
    :return: string describing the filter

    EVENT_FLAGS == xxxxx1: "undershoot" reset
    EVENT_FLAGS == xxxx1x: "overshoot" reset
    EVENT_FLAGS == xxx1xx: software sample
    EVENT_FLAGS == xx1xxx: fast signal chain triggered
    EVENT_FLAGS == x1xxxx: slow signal chain triggered
    EVENT_FLAGS == 1xxxxx: first event in MPU packet
    """
    if len(filter_flag.strip()) != 8:
        print ("Filter flag must have length of 8 characters")
        return
    # NICER only uses 6 bits for flagging so ignore the 1st 2 characters in flag
    fflag = filter_flag.strip()[2:]
    descrip = [
        "First Event in MPU packet",
        "Slow signal chain trigger",
        "Fast signal chain trigger",
        "Software sample",
        "Overshoot Reset",
        "Undershoot Reset"
    ]
    for i, d in enumerate(descrip):
        if fflag[i] != 'x':
            status = bool(np.byte(fflag[i]))
        else:
            status = 'ignored'
        print ("  {d} {stat}".format(d=d, stat=status))


def plot_gti_lc(obsid, rootdir, flagtype="slow", binwidth=2, ymax=30, save=False,
                chanmin=None, chanmax=None,
                figdir='/Users/corcoran/research/WR140/NICER/plots',
                figsize=[15, 4]):
    """
    plots the lightcurve for the specified obsid for all the gtis
    """

    nobs = nicerObs(obsid, rootdir)
    gti = nobs.get_gti()
    fig = plt.figure(figsize=figsize)

    nrows = int(len(gti) / 2)
    for i in range(2 * nrows):
        tstart = gti['START'][i]
        tstop = gti['STOP'][i]
        # print tstart,tstop
        subplot(nrows, 2, i + 1)
        fig.tight_layout(pad=1.2)
        ylim(0, ymax)
        plt.xlabel('Time - {0} (seconds)'.format(tstart), fontsize=16)
        plt.ylabel('XTI Counts s$^{-1}$', fontsize=16)
        if chanmin:
            titl = "{0} {1}-{2}".format(obsid, chanmin, chanmax)
        else:
            titl = obsid
        plt.title(titl)
        ctsbin, bincen, binwidths = nobs.get_lc(gtinum=i, binwidth=binwidth, flagtype=flagtype, chanmin=chanmin,
                                                chanmax=chanmax)
        plt.step(bincen - gti['START'][i], ctsbin / binwidth)
        if save:
            figname = os.path.join(figdir, "{0}_plot_gti.pdf".format(obsid))
            plt.savefig(figname)


def set_model():
    """
    Creates an XSPEC model instance for a two component absorbed thermal model plus gaussian line
    :return:
    """
    import xspec
    mo = xspec.Model("wabs*vapec + wabs*vapec + gaussian")
    mo.wabs.nH.values = [.1, 0.01, .05, .05, 100, 100]
    mo.vapec.kT.values = [3., 0.1, 1., 1., 9., 9.]
    mo.vapec.N.values = [3, 0.01, 1, 1, 30, 30]
    mo.vapec.norm.values = [1e-2, 0.001, 0, 0, 1, 1]
    mo.wabs_3.nH.values = [.1, 0.01, .05, .05, 100, 100]
    mo.vapec_4.norm.values = [0.1, 0.01, 0.0, 0.0, 1., 1.]
    mo.vapec_4.kT.values = [.1, 0.01, .1, .1, .5, .5]
    mo.gaussian.LineE.values = [6.4, .1, 6.2, 6.2, 6.6, 6.6]
    mo.gaussian.norm.values = [1e-5, 0.001, 0, 0, 0.0001, 0.0001]
    mo.gaussian.Sigma.values = [0.0, 0.01, 0.0, 0.0, .02, .02]
    return mo


def get_obsDF(obsid, model, datadir='/Volumes/SXDC/Data/NICER/wr140', interval=None):
    """
    Defines a pandas DataFrame summarizing the NICER observation id observation
    with blank spectrum parameters

    :param obsid: observation ID of the NICER observation (integer)
    :param model: model used to  fit the NICER spectrum
    :param datadir: location of the NICER data
    :param interval: if not None, append an "interval" number to the obsid; this is useful to divide an obsid spectrum by time
    :return: nicer Observation DataFrame
    """
    import pandas as pd
    obs = str(obsid)
    f = os.path.join(datadir, obs, 'xti/event_cl/ni{0}_0mpu7_cl.evt'.format(obs))
    hdu = fits.open(f)
    tstart = Time(hdu[1].header['DATE-OBS'])
    JDstart = (tstart.jd)
    tend = Time(hdu[1].header['DATE-END'])
    JDend = (tend.jd)
    Expos = (hdu[1].header['EXPOSURE'])
    JDmid = (tstart.jd + (tend.jd - tstart.jd) / 2.0)
    numgtis = (len(hdu[2].data))
    if interval:
        nobsid = "{0}_{1}".format(obsid, interval)
    else:
        nobsid = "{0}".format(obsid)
    nobsDict = {nobsid: {'JDSTART': JDstart, 'JDEND': JDend,
                             'JDMID': JDmid,
                             'EXPOSURE': Expos,
                             'Num_GTI': numgtis,
                             'Phase': np.nan,
                             'FLUX': np.nan,
                             'FluxBand': '',
                             'Fit_Statistic': np.nan,
                             'dof': np.nan
                             }
                }
    # add in spectrum parameters
    for c in model.componentNames:
        for p in model.__getattribute__(c).parameterNames:
            froz = model.__getattribute__(c).__getattribute__(p).frozen
            if not froz:
                nobsDict[nobsid]["{c}_{p}".format(c=c, p=p)] = np.nan
                # return parameter's Sigma by accessing the component/parameter dictionary
                nobsDict[nobsid]["{c}_{p}_err".format(c=c, p=p)] = np.nan
    nobsDF = pd.DataFrame(nobsDict)
    return nobsDF


def get_obsid_specparams(obsid, model=None, get_errors = True,
                         phaname=None,
                         rmffile='/Users/corcoran/Dropbox/nicer_cal/nicer_v0.06.rmf',
                         arffile='/Users/corcoran/Dropbox/nicer_cal/ni_xrcall_onaxis_v0.06.arf',
                         workdir="/Users/corcoran/research/WR140/NICER/work/",
                         datadir="/Volumes/SXDC/Data/NICER/wr140",
                         fluxband="2.0 10.0", statMethod="cstat",
                         ignore = "0.0-0.45, 7.5.0-**",
                         interval=None,
                         chatter=False
                         ):
    """Get spectrum parameters from fit
    gets the observation and spectrum parameters from the model fit
    for the given obsid.

    A NICER spectrum fit using the absorbed two-component thermal models
    (defined in the model1 function) should have been done prior to running
    this function.

    :param obsid: nicer observation id (integer)
    :param rmffile: nicer response file
    :param arffile: nicer effective area file
    :param workdir: user-defined nicer work directory
    :param datadir: user-defined directory holding nicer data
    :param phaname: name of phafile (with directory path); will be constructed if not specified
    """
    import xspec
    from heasarc.utils import xspec_utils as xu
    if interval is None:
        obs = str(obsid)
    else:
        obs = "{0}_{1}".format(obsid, interval)

    xspecdir = os.path.join(workdir, obs)
    if not phaname:
        phaname = os.path.join(xspecdir, 'ni{0}_0mpu7_cl.pha'.format(obsid))

    xspec.AllData.clear()

    try:
        pha = xspec.Spectrum(phaname)
        skip_calc = False
    except:
        print "Can't get flux for {0}".format(obsid)
        flux = np.nan
        skip_calc = True
        nobsDF = ''
    if not skip_calc:
        pha.response = rmffile
        pha.response.arf = arffile
        pha.ignore(ignore)
        #
        # read base model
        #
        if not model:
            modelname = os.path.join(xspecdir, 'ni{0}_0mpu7_cl_mo.xcm'.format(obsid))
            print("Reading {0}".format(modelname))
            model = xu.read_model_xcm(modelname, chatter=chatter)

        xspec.Fit.statMethod = statMethod
        xspec.Fit.perform()
        xspec.AllModels.calcFlux(fluxband)

        flux = pha.flux[0]
        print "{0}    flux = {1:.3e} {2}".format(obsid, flux, fluxband)
        modict = xu.get_mo_params(model, chatter=chatter)

        nobsDF = get_obsDF(obsid, model, datadir=datadir, interval=interval)

        # update JDSTART, JDEND, JDMID using GTI info from pha file

        hdu = fits.open(phaname)
        gti = list(hdu['GTI'].data)
        mjdoff = hdu['GTI'].header['MJDREFI'] + hdu['GTI'].header['MJDREFF']
        gtimjd = [[x / 86400.0 + mjdoff, y / 86400. + mjdoff, y-x] for x, y in gti]
        # print gtimjd
        gtijd = [[Time(x, format='mjd').jd, Time(y, format='mjd').jd, z] for x, y, z in gtimjd]
        # print gtijd
        # jdstart, jdend requires gtijd array to be time ordered
        jdstart = gtijd[0][0]
        jdend = gtijd[-1][1]
        nobsDF[obs]['JDSTART'] = jdstart
        nobsDF[obs]['JDEND'] = jdend
        nobsDF[obs]['JDMID'] = (jdend-jdstart)/2.0 + jdstart
        nobsDF[obs]['EXPOSURE'] = sum([y-x for x, y in gti])
        nobsDF[obs]['Num_GTI'] = len(gti)

        # store the spectral parameters in the data frame

        nobsDF[obs]['FLUX'] = flux
        nobsDF[obs]['FluxBand'] = fluxband
        nobsDF[obs]['Fit_Statistic'] = xspec.Fit.statistic
        nobsDF[obs]['dof'] = xspec.Fit.dof

        # get non-frozen model parameter values
        for c in model.componentNames:
            for p in model.__getattribute__(c).parameterNames:
                froz = model.__getattribute__(c).__getattribute__(p).frozen
                if not froz:
                    nobsDF[obs]["{c}_{p}".format(c=c, p=p)] = modict[c][p][0]
                    if get_errors:
                        # return parameter's Sigma by accessing the component/parameter dictionary
                        nobsDF[obs]["{c}_{p}_err".format(c=c, p=p)] = model.__getattribute__(c).__getattribute__(p).sigma
    return nobsDF


def concat_nobsDF(nobsDFlist):
    """
    concatenates a list of nicer observation DataFrames
    :param nobsDFlist: list of nicer dataframes (as constructed by
    get_obsid_specparams or get_obsDF)
    """
    import pandas as pd
    nobsDFconcat = pd.concat(nobsDFlist, axis=1)
    return nobsDFconcat


def set_xspec(obsid, model = None,
              rmffile='/Users/corcoran/Dropbox/nicer_cal/nicer_v0.06.rmf',
              arffile='/Users/corcoran/Dropbox/nicer_cal/ni_xrcall_onaxis_v0.06.arf',
              workdir='/Users/corcoran/research/WR140/NICER/work/',
              ignore='0.0-0.45, 5.-**', showplot=False, showmodel=False
              ):
    """
    sets the pha and model instances for a given obsid
    :param obsid: NICER observation id (integer)
    :param rmffile: NICER response file
    :param arffile: NICER effective area file
    :param workdir: NICER dataset working directory
    :param ignore: energy range in keV to ignore when fitting
    :param showplot: if True plot the model and spectrum vs. energy
    :param showmodel: if True print the model parameters
    :return:
    """
    import xspec
    import matplotlib as plt
    obs = str(obsid)

    xspec.AllData.clear()
    xspec.AllModels.clear()

    xspecdir = os.path.join(workdir, obs)
    phaname = os.path.join(xspecdir, 'ni{obs}_0mpu7_cl.pha'.format(obs=obsid))
    print "phaname = {phaname}".format(phaname=phaname)

    try:
        pha = xspec.Spectrum(phaname)
    except:
        print "Can't find {phaname}; returning".format(phaname=phaname)
        return 0, 0
    pha.response = rmffile
    pha.response.arf = arffile
    pha.ignore(ignore)

    #
    # Define a model
    #
    if not model:
        model = set_model()
    if showmodel:
        with sys_pipes():
            model.show()
    if showplot:
        xspec.Plot.setRebin(minSig=3, maxBins=30)
        xspec.Plot.device = "/null"
        xspec.Plot.xAxis = "keV"
        xspec.Plot.yLog = "True"
        xspec.Plot("data")

        plt.figure(figsize=[10, 6])
        plt.yscale('log')
        plt.xscale('log')
        plt.xlabel('Energy (keV)', fontsize=16)
        plt.step(xspec.Plot.x(), xspec.Plot.y())
        plt.step(xspec.Plot.x(), xspec.Plot.model())

    return pha, model


def fit_spectrum(obsid, pha, model, writexcm=True,
                 workdir='/Users/corcoran/research/WR140/NICER/work/',
                 statMethod='cstat'
                 ):
    import xspec
    from wurlitzer import sys_pipes
    import pylab as plt
    from heasarc.utils import xspec_utils as xu
    if type(pha) != int:
        #
        # do fit
        #
        xspec.Fit.statMethod = statMethod
        xspec.Fit.perform()
        print("Best Fit Model is\n")
        with sys_pipes():
            model.show()
        pha.notice("0.4-10.0")
        xspec.Plot.setRebin(minSig=3, maxBins=30)
        xspec.Plot.device = "/null"
        xspec.Plot.xAxis = "keV"
        xspec.Plot.yLog = "True"
        xspec.Plot("data")
        plt.figure(figsize=[10, 6])
        plt.yscale('log')
        plt.xscale('log')
        plt.xlabel('Energy (keV)', fontsize=16)
        plt.title("{obs}".format(obs=obsid), fontsize=16)
        plt.errorbar(xspec.Plot.x(), xspec.Plot.y(),
                 xerr=xspec.Plot.xErr(), yerr=xspec.Plot.yErr(), fmt='.')
        plt.step(xspec.Plot.x(), xspec.Plot.model(), where="mid")
        band = "0.5-10 keV"
        xspec.AllModels.calcFlux(band.replace(' keV', '').replace('-',' '))
        print "Flux is {0:.3e} in the  {1} band".format(pha.flux[0], band)
        if writexcm:
            xcmfile = os.path.join(workdir, str(obsid), 'ni{obsid}_0mpu7_cl'.format(obsid=obsid))
            xu.write_xcm(xcmfile, pha, model=model)
    else:
        print "Can't fit OBSID {obs}".format(obs=obsid)
    return pha, model

########################
# TESTS
########################

def test_filter_flag():
    print Time.now()
    efile = '/Volumes/SXDC/Data/NICER/wr140/1120010113/xti/event_cl/ni1120010113_0mpu7_cl.evt.gz'
    em = filter_flag(efile)
    print("total number of events             = {em}".format(em=len(em)))
    ind = np.where(np.asarray(em) == True)[0]
    print("number of events which pass filter = {iem}".format(iem=len(ind)))
    print Time.now()
    return

def test_get_specparams_obsid():
    datadir = '/Volumes/SXDC/Data/NICER/etacar'
    workdir = "/Users/corcoran/research/ETA_CAR/NICER/work/"

    rmffile = '/Users/corcoran/Dropbox/nicer_cal/nicer_v0.06.rmf'
    arffile = '/Users/corcoran/Dropbox/nicer_cal/ni_xrcall_onaxis_v0.06.arf'

    nobsDF = get_obsid_specparams(o, workdir=workdir, datadir=datadir,
                                 get_errors = True)

def test_lc_detid(det_id):
    """
    Tests light curve creation with specified detector id
    :param det_id:
    :return:
    """
    nobs = nicerObs(str(1114010119), rootdir='/Volumes/SXDC/Data/NICER/hr1099/repro')
    nobsDF = nobs.get_eventsdf()
    cts, time, err = nobs.get_lc(binwidth=1., det_id=det_id)
    return cts, time, err


if __name__ == '__main__':
    # obsids = ['1706280502',
    #           '1706290110',
    #           '1706301133',
    #           '1707050057',
    #           '1707061816',
    #           '1707070511']
    #
    # # rootdir = '/Users/corcoran/program/missions/NICER:OSWG/sample_data/nicer-sample-data_from_workshop/Early_Data_ObsSci_WG/GRS_1915+105'
    # # nobs = nicerObs(obsids[0], rootdir)
    # # ctsbin, bins = nobs.get_lc()
    # # gti=nobs.get_gti()
    # # ctsbin, phi = nobs.fold(evttype='cl',period=7.0, tstart=gti['START'][0],tstop=gti['STOP'][0],nbins=10)
    #
    # rootdir = '/Users/corcoran/program/missions/NICER:OSWG/sample_data/nicer-sample-data_from_workshop/Early_Data_ObsSci_WG/GRS_1915+105'
    # nobs = nicerObs(obsids[5], rootdir)
    # gti = nobs.get_gti()
    # print len(gti)
    #
    # i = 2
    #
    # tstart = gti['START'][i]
    # tstop = gti['STOP'][i]
    # ctsbin, bincen = nobs.get_lc(tstart=tstart, tstop=tstop, binwidth=1.)
    # obsids = ['1706280502',
    #           '1706290110',
    #           '1706301133',
    #           '1707050057',
    #           '1707061816',
    #           '1707070511']
    #
    # rootdir = '/Users/corcoran/program/missions/NICER:OSWG/sample_data/nicer-sample-data_from_workshop/Early_Data_ObsSci_WG/GRS_1915+105'
    # nobs = nicerObs(obsids[0], rootdir)
    # gti = nobs.get_gti()
    # print len(gti)
    #
    # i = 3
    #
    #
    # tstart = gti['START'][i]
    # tstop = gti['STOP'][i]
    # print tstart, tstop
    # ctsbin, bincen = nobs.get_lc(tstart=tstart, tstop=tstop, binwidth=5)
    # ctsbin, bincen = nobs.fold(evttype='cl', nbins=100, period=8, tstart=tstart, tstop=tstop)
    # datadir = "/Volumes/BigDrive/Data/NICER/ucep"
    # obsid = '1100140101'
    # obsid = '1012070128'
    # datadir = '/Volumes/BigDrive/Data/NICER/bkg'
    # obsid = '1012010113'
    # nobs = nicerObs(obsid, datadir)
    # gti = nobs.get_gti()
    # bincts, bincen, binwidths = nobs.get_lc(200., gtinum=0)
    # print bincts
    #
    ##### test_filter_flag()
    #test_lc_detid(10)

    nobs = nicerObs('1120010136', rootdir='/Volumes/SXDC/Data/NICER/wr140')
    eventDF = nobs.get_eventsdf(flagtype='slow')