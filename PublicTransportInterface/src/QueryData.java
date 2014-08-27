import java.io.IOException;
import java.util.List;
import java.util.Date;

import de.schildbach.pte.BahnProvider;
import de.schildbach.pte.NetworkProvider;
import de.schildbach.pte.NetworkProvider.Accessibility;
import de.schildbach.pte.NetworkProvider.WalkSpeed;
import de.schildbach.pte.dto.Location;
import de.schildbach.pte.dto.LocationType;
import de.schildbach.pte.dto.NearbyStationsResult;
import de.schildbach.pte.dto.Product;
import de.schildbach.pte.dto.QueryDeparturesResult;
import de.schildbach.pte.dto.QueryTripsResult;

public class QueryData {

    private NetworkProvider provider;

    public QueryData() {
        this.provider = new BahnProvider();
    }

    public Location createAddressObject(int latitude, int longitude) {
        return new Location(LocationType.ADDRESS, latitude, longitude);
    }

    public QueryTripsResult calculateConnection(Location from, Location to, int delay) {
        Date departureDate = new Date( System.currentTimeMillis() + delay*60000 );
        try {
            return provider.queryTrips(
                    from, null, to, departureDate, true, Product.ALL,
                    WalkSpeed.SLOW, Accessibility.NEUTRAL, null);
        } catch (IOException e) {
            return null;
        }        
    }

    public QueryDeparturesResult getDepartures(int stationID, int numberOfResults) {
        try {
            return provider.queryDepartures( stationID, numberOfResults, false);
        } catch (IOException e) {
            return null;
        }        
    }

    public NearbyStationsResult getNearestStations(int latitude, int longitude) {
        try {
            return provider.queryNearbyStations(new Location(LocationType.ADDRESS, latitude, longitude), 0, 0);
        } catch (IOException e) {
            return null;
        }        
    }

}
