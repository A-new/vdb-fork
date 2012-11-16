'''
Visgraph supports backing the graph objects with a postgres db.
'''

import psycopg2

import visgraph.graphcore as vg_graphcore

init_db = '''
    DROP TABLE IF EXISTS vg_edges;
    CREATE TABLE vg_edges (
        eid     BIGSERIAL,
        n1      BIGINT,
        n2      BIGINT,
        created TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (eid)
    );
    CREATE INDEX vg_edges_idx_n1 ON vg_edges (n1);
    CREATE INDEX vg_edges_idx_n2 ON vg_edges (n2);

    DROP TABLE IF EXISTS vg_edge_props;
    CREATE TABLE vg_edge_props (
        eid     BIGINT,
        pname   VARCHAR(256) NOT NULL,
        intval  BIGINT,
        strval  VARCHAR(1024),
        created TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (eid, pname)
    );
    CREATE INDEX vg_edge_eid_idx ON vg_edge_props (eid);
    CREATE INDEX vg_edge_pname_intval ON vg_edge_props (pname, intval);
    CREATE INDEX vg_edge_pname_strval ON vg_edge_props (pname, strval);

    DROP TABLE IF EXISTS vg_nodes;
    CREATE TABLE vg_nodes (
        nid     BIGSERIAL,
        created TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY(nid)
    );

    DROP TABLE IF EXISTS vg_node_props;
    CREATE TABLE vg_node_props (
        nid     BIGINT NOT NULL,
        pname   VARCHAR(255) NOT NULL,
        intval  BIGINT,
        strval  VARCHAR(1024),
        created TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY  (nid,pname)
    );
    CREATE INDEX vg_node_nid_idx ON vg_node_props (nid);
    CREATE INDEX vg_node_pname_intval ON vg_node_props (pname, intval);
    CREATE INDEX vg_node_pname_strval ON vg_node_props (pname, strval);
'''

# Exanmple database creds...
default_dbinfo = {
'user':'visgraph',
'password':'ohhai!',
'database':'visgraph',
# Add host if you want...
}

def initGraphDb(dbinfo):
    db = psycopg2.connect(**dbinfo)
    c = db.cursor()
    c.execute(init_db)
    c.close()
    db.commit()
    db.close()

class DbGraphStore:
    '''
    A DbGraphStore object may be used for all the standard management
    of node and edge information but may not be used for path queries.

    FIXME possibly make it able to do path queries but *really* slow?

    Use the buildSubGraph() API to pull path serchable graphs out of
    the DBGraphStore.
    '''
    def __init__(self, dbinfo=None):
        if dbinfo == None:
            dbinfo = default_dbinfo
        self.dbinfo = dbinfo
        self.db = psycopg2.connect(**dbinfo)
        self.autocommit = True

    def _doSelect(self, query, *args):
        '''
        For now, a fetchall based select wrapper.
        '''
        c = self.db.cursor()
        try:
            c.execute(query, args)
            return c.fetchall()
        finally:
            c.close()

    def _doInsert(self, query, *args):
        '''
        Standard insert wrapper.
        '''
        c = self.db.cursor()
        c.execute(query, args)
        c.close()
        if self.autocommit:
            self.db.commit()

    def _doUpdate(self, query, *args):
        '''
        Do an update with 'returning' syntax to know
        if an update was made.
        '''
        res = []
        c = self.db.cursor()
        c.execute(query, args)
        res = c.fetchall()
        c.close()
        if self.autocommit:
            self.db.commit()
        return res

    def _doInsertRetId(self, query, *args):
        '''
        Insert with a returning value.
        '''
        c = self.db.cursor()
        c.execute(query, args)
        hid = c.fetchall()[0][0]
        c.close()
        if self.autocommit:
            self.db.commit()
        return hid

    def _doCommit(self):
        self.db.commit()

    def addNode(self, nodeid=None, ninfo=None, **kwargs):
        if nodeid != None:
            raise Exception('DbGraphStore Manages nodeid!')
        q = 'INSERT INTO vg_nodes DEFAULT VALUES RETURNING nid'
        nid = self._doInsertRetId(q)

        if ninfo != None:
            kwargs.update(ninfo)

        for key,val in kwargs.items():
            self.setNodeInfo(nid, key, val)

        return nid

    def delEdge(self, eid):
        '''
        Delete an edge from the graph database.

        Example: g.delEdge(eid)
        '''
        q = '''
        DELETE FROM
            vg_edge_props
        WHERE
            eid = %s
        '''
        self._doInsert(q, eid)
        q = '''
        DELETE FROM
            vg_edges
        WHERE
            eid = %s
        '''
        self._doInsert(q, eid)

    def delNode(self, nid):
        '''
        Delete the given node (and his edges) from the graph dbase.

        Example: g.delNode(nid)

        NOTE: this will delete any edges which go to or from nid!
        '''
        for eid,n1,n2,einfo in self.getRefsFrom(nid):
            self.delEdge(eid)
        for eid,n1,n2,einfo in self.getRefsTo(nid):
            self.delEdge(eid)
        q = '''
        DELETE FROM
            vg_node_props
        WHERE
            nid = %s
        '''
        self._doInsert(q, nid)
        q = '''
        DELETE FROM
            vg_nodes
        WHERE
            nid = %s
        '''
        self._doInsert(q, nid)

    def setNodeInfo(self, nid, pname, value):
        if isinstance(value, int) or isinstance(value, long):
            q = 'UPDATE vg_node_props SET intval=%s WHERE nid=%s and pname=%s RETURNING nid'
            q1 = 'INSERT INTO vg_node_props (nid, pname, intval) VALUES (%s,%s,%s)'
        else:
            q = 'UPDATE vg_node_props SET strval=%s WHERE nid=%s and pname=%s RETURNING nid'
            q1 = 'INSERT INTO vg_node_props (nid, pname, strval) VALUES (%s,%s,%s)'
        # return a value to see if we actually did the update...
        res = self._doSelect(q, value, nid, pname)
        if len(res) == 0:
            self._doInsert(q1, nid, pname, value)
        if self.autocommit:
            self.db.commit()

    def getNodeInfo(self, nid, pname, default=None):
        q = 'SELECT intval,strval from vg_node_props WHERE nid=%s AND pname=%s'
        res = self._doSelect(q, nid, pname)
        if len(res) == 0:
            return default
        intval, strval = res[0]
        if intval != None:
            return intval
        return strval

    def delNodeInfo(self, nid, pname):
        q = 'DELETE FROM vg_node_props WHERE nid=%s AND pname=%s'
        self._doInsert(q, nid, pname)

    def getNodeProps(self, nid):
        ret = {}
        q = 'SELECT pname,intval,strval FROM vg_node_props WHERE nid=%s'
        for pname,intval,strval in self._doSelect(q, nid):
            if intval != None:
                ret[pname] = intval
            else:
                ret[pname] = strval
        return ret

    def addEdge(self, fromid, toid, eid=None, einfo=None):
        if eid != None:
            raise Exception('DbGraphStore Manages eid!')
        if fromid == None:
            raise Exception('Invalid from id (None)!')
        if toid == None:
            raise Exception('Invalid to id (None)!')
        q = 'INSERT INTO vg_edges (n1, n2) VALUES (%s, %s) RETURNING eid'
        eid = self._doInsertRetId(q, fromid, toid)
        if einfo != None:
            for key,val in einfo.items():
                self.setEdgeInfo(eid, key, val)
        return eid

    def getRefsFrom(self, nodeid):
        '''
        Return a list of edges which originate with us.

        Example: for eid, fromid, toid, einfo in g.getRefsFrom(id)
        '''
        q = '''
        SELECT
            vg_edges.*,
            vg_edge_props.*
        FROM
            vg_edges,
            vg_edge_props
        WHERE
            vg_edges.n1 = %s AND
            vg_edges.eid = vg_edge_props.eid
        '''
        refs = {}
        res = self._doSelect(q, nodeid)
        for eid,n1,n2,created,eid1,pname,intval,strval,created1 in res:
            r = refs.get(eid)
            if r == None:
                r = (eid, n1, n2, {})
                refs[eid] = r

            if intval != None:
                r[3][pname] = intval
            else:
                r[3][pname] = strval

        return refs.values()

    def getRefsTo(self, nodeid):
        '''
        Return a list of edges which we reference.

        Example: for eid, fromid, toid, einfo in g.getRefsTo(id)
        '''
        q = '''
        SELECT
            vg_edges.*,
            vg_edge_props.*
        FROM
            vg_edges,
            vg_edge_props
        WHERE
            vg_edges.n2 = %s AND
            vg_edges.eid = vg_edge_props.eid
        '''
        refs = {}
        res = self._doSelect(q, nodeid)
        for eid,n1,n2,created,eid1,pname,intval,strval,created1 in res:
            r = refs.get(eid)
            if r == None:
                r = (eid, n1, n2, {})
                refs[eid] = r

            if intval != None:
                r[3][pname] = intval
            else:
                r[3][pname] = strval

        return refs.values()

    def setEdgeInfo(self, eid, pname, value):
        if isinstance(value, int) or isinstance(value, long):
            q = 'UPDATE vg_edge_props SET intval=%s WHERE eid=%s and pname=%s RETURNING eid'
            q1 = 'INSERT INTO vg_edge_props (eid, pname, intval) VALUES (%s,%s,%s)'
        else:
            q = 'UPDATE vg_edge_props SET strval=%s WHERE eid=%s and pname=%s RETURNING eid'
            q1 = 'INSERT INTO vg_edge_props (eid, pname, strval) VALUES (%s,%s,%s)'
        # return a value to see if we actually did the update...
        res = self._doSelect(q, value, eid, pname)
        if len(res) == 0:
            self._doInsert(q1, eid, pname, value)

    def getEdgeInfo(self, eid, pname, default=None):
        q = 'SELECT intval,strval from vg_edge_props WHERE eid=%s AND pname=%s'
        res = self._doSelect(q, eid, pname)
        if len(res) == 0:
            return default
        intval, strval = res[0]
        if intval != None:
            return intval
        return strval

    def searchNodes(self, propname, propval=None):
        '''
        Return (but do not cache forward) the nid's of nodes which
        have a property with the following name (and optionally, value).

        Example:
            for nid in g.searchNodes('woot', 10)
                print g.getNodeInfo(nid, 'name')
            
        NOTE: This is specific to the DbGraphStore...
        '''
        if propval == None:
            q = 'SELECT nid FROM vg_node_props WHERE pname=%s'
            c = self.db.cursor()
            c.execute(q, (propname,))
            for row in c:
                yield row
            c.close()

    def buildSubGraph(self):
        '''
        Return a subgraph which may be used to populate from the DB and
        do path searching.
        '''
        return DbSubGraph(self.dbinfo)

class DbSubGraph(DbGraphStore, vg_graphcore.Graph):

    '''
    A subgraph in the database is basically a forward cached instance of selected
    nodes and edges in an in-memory graph (visgraph.graphcore.Graph).  This object
    may then be used for traditional path tracing without going back to the database.

    Any modifications to graph element properties *will* be synchronized back to the
    database backing the given subgraph.
    '''

    def __init__(self, dbinfo):
        vg_graphcore.Graph.__init__(self)
        DbGraphStore.__init__(self, dbinfo)

    def addNode(self, nodeid=None, ninfo=None, **kwargs):
        # Do *both*
        nid = DbGraphStore.addNode(self, nodeid=nodeid, ninfo=ninfo, **kwargs)
        vg_graphcore.Graph.addNode(self, nodeid=nid, ninfo=None, **kwargs)
        return nid

    def addEdge(self, fromid, toid, einfo):
        eid = DbGraphStore.addEdge(self, fromid, toid, einfo=einfo)
        vg_graphcore.Graph.addEdge(self, fromid, toid, eid=eid, einfo=None)
        return eid

    def useEdges(self, **kwargs):
        '''
        Pull some edges from the DbStore backing this subgraph into the actual
        visgraph.graphcore.Graph instance so path traversal is possible.
        '''
        done = {}
        for key,val in kwargs.items():
            if type(val) in (int,long):
                # FIXME is vg_edges.eid faster or vg_edge_props?
                q = 'SELECT vg_edges.eid,n1,n2 FROM vg_edge_props,vg_edges WHERE pname=%s AND intval=%s AND vg_edges.eid=vg_edge_props.eid'
            else:
                q = 'SELECT vg_edges.eid,n1,n2 FROM vg_edge_props,vg_edges WHERE pname=%s AND strval=%s AND vg_edges.eid=vg_edge_props.eid'
            for eid,n1,n2 in self._doSelect(q, key, val):
                print 'using: %d (%d->%d)' % (eid, n1, n2)
                done[eid] = (eid, n1, n2)

        # FIXME add the nodes for these edges
        for eid, n1, n2 in done.values():
            if vg_graphcore.Graph.getNode(self, n1) == None:
                vg_graphcore.Graph.addNode(self, nodeid=n1)
            if vg_graphcore.Graph.getNode(self, n2) == None:
                vg_graphcore.Graph.addNode(self, nodeid=n2)
            vg_graphcore.Graph.addEdge(self, n1, n2, eid=eid)

    def expandNode(self, nid, maxdepth=1):
        '''
        Add *all* the edges (and adjacent nodes) by traversing this nodes
        edges to the specified depth...
        '''
        todo = [(nid, 0),]
        print 'INITIAL EXPAND',nid
        if vg_graphcore.Graph.getNode(self, nid) == None:
            print 'EXPANDING',nid
            vg_graphcore.Graph.addNode(self, nodeid=nid)

        while len(todo):
            nid,depth = todo.pop()

            if depth > maxdepth:
                continue

            # Do expansion based on the *database*
            q = 'SELECT eid,n2 FROM vg_edges WHERE n1=%s'
            for eid, n2 in self._doSelect(q, nid):
                if vg_graphcore.Graph.getNode(self, n2) == None:
                    print 'EXPANDING',n2
                    vg_graphcore.Graph.addNode(self, nodeid=n2)
                if vg_graphcore.Graph.getEdge(self, eid) == None:
                    vg_graphcore.Graph.addEdge(self, nid, n2, eid=eid)
                ndepth = depth+1
                if ndepth < maxdepth:
                    todo.append((n2, ndepth))

    # pullNode?
    # expandNode?

