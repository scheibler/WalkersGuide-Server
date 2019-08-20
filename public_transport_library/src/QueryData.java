import java.io.IOException;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.Map;

import com.google.common.base.Charsets;

import de.schildbach.pte.AbstractNetworkProvider;
import de.schildbach.pte.DbProvider;
import de.schildbach.pte.NetworkId;
import de.schildbach.pte.NetworkProvider;
import de.schildbach.pte.RtProvider;
import de.schildbach.pte.VvoProvider;

import de.schildbach.pte.dto.Location;
import de.schildbach.pte.dto.LocationType;
import de.schildbach.pte.dto.NearbyLocationsResult;
import de.schildbach.pte.dto.Point;
import de.schildbach.pte.dto.QueryDeparturesResult;


public class QueryData {

    private static final String USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.108 Safari/537.36";
    private static final Map<String,AbstractNetworkProvider> supportedNetworkProviderMap;

    static {
        Map<String,AbstractNetworkProvider> staticMap = new LinkedHashMap<String,AbstractNetworkProvider>();
        staticMap.put(
                NetworkId.RT.name(),
                new RtProvider());
        staticMap.put(
                NetworkId.DB.name(),
                new DbProvider(
                    "{\"type\":\"AID\",\"aid\":\"n91dB8Z77MLdoR0K\"}",
                    "bdI8UVj40K5fvxwf".getBytes(Charsets.UTF_8)));
        staticMap.put(
                NetworkId.VVO.name(),
                new VvoProvider());
        supportedNetworkProviderMap = Collections.unmodifiableMap(staticMap);
    }

    public static ArrayList<String> getSupportedNetworkProviderIdList() {
        return new ArrayList<String>(supportedNetworkProviderMap.keySet());
    }

    public static NetworkProvider getNetworkProvider(String networkProviderId) {
        AbstractNetworkProvider provider = supportedNetworkProviderMap.get(networkProviderId);
        if (provider != null) {
            provider.setUserAgent(USER_AGENT);
        }
        return provider;
    }

    public static NearbyLocationsResult getNearbyStations(
            NetworkProvider provider, double latitude, double longitude) {
        Location location = new Location(
                LocationType.COORD, null, Point.fromDouble(latitude, longitude));
        try {
            return provider.queryNearbyLocations(
                    EnumSet.of(LocationType.STATION), location, 250, 10);
        } catch (IOException e) {
            System.out.println("getNearbyStations error: " + e.getMessage());
            e.printStackTrace();
            return null;
        }        
    }

    public static QueryDeparturesResult getDepartures(NetworkProvider provider, String stationID) {
        try {
            return provider.queryDepartures(stationID, new Date(), 100, false);
        } catch (IOException e) {
            System.out.println("queryDepartures error: " + e.getMessage());
            e.printStackTrace();
            return null;
        }        
    }

}
